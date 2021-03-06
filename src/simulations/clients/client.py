##
# Mouse Locomotion Simulation
#
# Human Brain Project SP10
#
# This project provides the user with a framework based on 3D simulators allowing:
#  - Edition of a 3D model
#  - Edition of a physical controller model (torque-based or muscle-based)
#  - Edition of a brain controller model (oscillator-based or neural network-based)
#  - Simulation of the model
#  - Optimization and Meta-optimization of the parameters in distributed cloud simulations
#
# File created by: Gabriel Urbain <gabriel.urbain@ugent.be>
#                  Dimitri Rodarie <d.rodarie@gmail.com>
# February 2016
##
import copy
import logging
import threading
import time
from threading import Thread, Lock

import rpyc
from rpyc.utils.factory import DiscoveryError
from rpyc.utils.registry import UDPRegistryClient, REGISTRY_PORT
from simulations import PROTOCOL_CONFIG
from simulations import Registry
from utils import Observable

from .connection import ServerInfo, SimulationRequest, Connexion

REQUESTS = {"Simulation": "simulation", "Test": "test"}


class Client(Observable):
    """
    Client class provides a high level interface to distribute a large number of
    simulation requests in a variable size computation cloud using tools like asynchronous
    request and registry server to monitor the network state via UDP requests.
    Usage:
            # Create and start Client thread
            sc = Client()
            sc.start()

            # Send simulation list and wait for results
            sim_list = [opt1 opt2]
            res_list = sc.simulate(sim_list)

            # Wait to terminate all work and stop Client thread
            sc.stop()
    """

    def __init__(self, opt):
        """
        Class initialization
        :param opt: Dictionary containing simulation parameters
        """
        Observable.__init__(self)
        # Simulation list stacks
        self.rqt = []
        self.rsp = []
        self.cloud_state = dict()  # dictionary of server state on the cloud. Entries are server hashes
        self.server_list = []  # list of active servers
        self.conn_list = []  # list of active RPYC connections
        # Server parameters
        self.simulator = opt["simulator"]
        self.ip_register = opt['register_ip'] if 'register_ip' in opt else None
        # Simulation client parameter
        self.rqt_n = 0
        self.sim_prun_t = 0.1
        self.mng_prun_t = 0.1
        self.mng_stop = False
        self.bg_async_threads = []
        self.reg_found = True
        self.terminated = False
        self.interrupted = False
        self.interrupt_to = 3
        self.server_dispo = False
        self.t_sim_init = 0
        self.sim_time = 0
        self.sim_timeout = opt["timeout"]
        self.results = {}
        # Threading
        self.mutex_cloud_state = Lock()
        self.mutex_conn_list = Lock()
        self.mutex_rsp = Lock()
        self.mutex_rqt = Lock()
        self.mutex_res = Lock()

        self.thread = None
        logging.debug("Sim Client initialization achieved. Number of active threads = " +
                      str(threading.active_count()))

    def __refresh_cloud_state(self):
        """Refresh the cloud state list using the registry server"""

        # Check network with rpyc registry thread
        try:
            self.server_list = rpyc.discover((self.simulator + "sim").capitalize(),
                                             registrar=UDPRegistryClient(ip=self.ip_register, port=REGISTRY_PORT))
            logging.debug("Server list " + str(self.server_list))
        except DiscoveryError:
            if self.reg_found:
                logging.info("No simulation Server found on the network!")
                self.reg_found = False
                self.server_list = []

        if self.server_list and not self.reg_found:
            logging.info("Simulation Server(s) found on the network: " + str(self.server_list))
            self.reg_found = True

        # Transform server list into a dict
        serv_list_dict = []
        for item in map(lambda x: ServerInfo(x[0], x[1]), self.server_list):
            serv_list_dict.append(item)
        serv_dict = dict(zip(map(hash, self.server_list), serv_list_dict))

        # Create sets for server_dict and cloud_state
        keys_serv_dict = set(serv_dict.keys())
        keys_cloud_state = set(self.cloud_state.keys())

        # Compare and update cloud_state set if needed
        for elem in keys_serv_dict.difference(keys_cloud_state):
            if len(self.rqt) > 0:
                self.mutex_cloud_state.acquire()
                self.cloud_state[elem] = serv_dict[elem]
                self.cloud_state[elem].status = True
                self.cloud_state[elem].nb_threads = 0
                self.mutex_cloud_state.release()

        for elem in keys_cloud_state.difference(keys_serv_dict):
            self.mutex_cloud_state.acquire()
            self.cloud_state.pop(elem)
            self.mutex_cloud_state.release()

        logging.debug("Server list " + str(self.server_list) + " cloud " + str(self.cloud_state))

    def __select_candidate(self):
        """
        Select the most suited candidate in the simulation cloud.
        :return: Int id of the best candidate, 0 if there is no good candidate
        """

        # We check registry_server for new server (adding it as empty one)
        self.__refresh_cloud_state()
        logging.debug("List of registered simulation computers: " + str(self.server_list))

        # We select an available server on the cloud_state list minimizing thread numbers
        self.check_sim()
        self.mutex_cloud_state.acquire()
        # Select the server with the largest number of simulations available
        cloud_list = self.cloud_state.items()
        if len(self.cloud_state) >= 2:
            cloud_list = sorted(cloud_list, key=lambda x: x[1].nb_threads, reverse=False)
        for item in cloud_list:
            key = item[0]
            if self.cloud_state[key].status:
                self.mutex_cloud_state.release()
                return key
        self.mutex_cloud_state.release()
        return 0

    @staticmethod
    def rpyc_casting(rsp):
        """
        Return a casted rpyc response
        :param rsp: rpyc response to cast
        :return: casted result
        """

        try:
            cast = rsp.value
            if not type(rsp.value) == str:
                cast = eval(str(cast))
            return cast
        except Exception as e:
            exception = "Impossible to cast the result. Exception:\n" + str(e)
            logging.error(exception)
            return exception

    def response_simulation(self, rsp):
        """
        Callback function called when a simulation has finished
        :param rsp: rpyc response to process
        """

        def function(server_id, rsp_):
            """
            Function to process the simulation results
            :param server_id: Int Server id for the cloud
            :param rsp_: rpyc response to process
            """

            # We add the rsp from the simulation to the rsp list
            for simulation in self.results[server_id]:
                if simulation.callback == rsp_:
                    self.mutex_rsp.acquire()
                    self.rsp[simulation.index] = copy.copy(self.rpyc_casting(rsp_))
                    self.mutex_rsp.release()
                    break

            # Notify observer about the new result
            self.notify_observers(**{"res": self.rsp})

            # Decrease thread number in cloud_state dict
            self.mutex_cloud_state.acquire()
            self.cloud_state[server_id].nb_threads -= 1
            self.mutex_cloud_state.release()

        self.__process_callback(rsp, function)

    def response_test(self, rsp):
        """
        Callback function called when a simulation test has finished
        :param rsp: rpyc response to process
        """

        def function(server_id, rsp_):
            """
            Function to process the simulation test results
            :param server_id: Int Server id for the cloud
            :param rsp_: rpyc response to process
            """
            rsp_cast = self.rpyc_casting(rsp_)
            if type(rsp_cast) == dict:
                logging.info("Test server " + self.cloud_state[server_id].address + ":" +
                             str(self.cloud_state[server_id].port) + " consumptions:\n" +
                             "Common:{\n\tCPU = " + str(rsp_cast["common"]["CPU"]) +
                             "\n\tMemory = " + str(rsp_cast["common"]["memory"]) + "\n}," +
                             self.simulator + ":{\n\tCPU = " + str(rsp_cast[self.simulator]["CPU"]) +
                             "\n\tMemory = " + str(rsp_cast[self.simulator]["memory"]) + "\n}")
            else:
                logging.error("Impossible to cast the results.")

        self.__process_callback(rsp, function)

    def __process_callback(self, rsp, function):
        """
        Default callback function called at the end of every service
        :param rsp: rpyc response to process
        :param function: Function to process the simulation results
        """

        if not rsp.error:
            conn_found = False
            for item in self.conn_list:
                if rsp._conn.__hash__() == item.connexion.__hash__():  # The server has been requested from this client
                    conn_found = True
                    server_id = item.server_id
                    if server_id in self.cloud_state:  # The server is still in the cloud
                        function(server_id, rsp)
                        logging.info("Response received from server " + str(self.cloud_state[server_id].address) +
                                     ":" + str(self.cloud_state[server_id].port))

                        # Remove clean simulation callback from the list
                        self.del_clean_simulation(server_id, rsp)
                    else:
                        logging.error("Server " + str(server_id) +
                                      " not in the list anymore. Please check connection to ensure simulation results.")
                    # Close connection and listening thread
                    # As soon as we stop the thread, the function is directly exited because the callback
                    # function is handle by the thread itself

                    logging.info("Deletion of connection: " + str(item.connexion.__hash__()))
                    item.connexion.close()
                    t = item.thread
                    self.mutex_conn_list.acquire()
                    self.conn_list.remove(item)
                    self.mutex_conn_list.release()
                    t._active = False
                    break

            # If no candidate in the list
            if not conn_found:
                logging.error("Connection " + str(rsp._conn.__hash__()) +
                              " not in the list anymore. Please check connection to ensure simulation results.")
        else:
            logging.error('Client.process_callback() : The simulation server return an exception\n')

    def simulate(self, sim_list):
        """Perform synchronous simulation with the given list and return response list"""

        # If rqt list is empty
        if not self.rqt:

            # Create a request list and reset results
            self.mutex_rqt.acquire()
            for k, v in enumerate(sim_list):
                self.rqt.append(SimulationRequest(v, k))
            sim_n = len(sim_list)
            self.rqt_n += sim_n
            self.mutex_rqt.release()
            self.mutex_rsp.acquire()
            self.rsp = list()
            for i in range(self.rqt_n):
                self.rsp.append({})
            self.mutex_rsp.release()
            # Check for simulation and interrupt when processed or interrupted
            to = 0
            to_init = 0
            simulation_running = True
            time.sleep(1)
            while (self.rqt or simulation_running) and not self.terminated and to < self.interrupt_to:
                simulation_running = False
                for result in self.results.values():
                    if len(result) != 0:
                        simulation_running = True
                        break
                if self.interrupted:
                    to = time.time() - to_init
                try:
                    time.sleep(self.sim_prun_t)
                except KeyboardInterrupt:
                    logging.warning("Simulation interrupted by user!")
                    self.notify_observers(**{"interruption": True})
                    self.stop()
                    to_init = time.time()
                    self.interrupted = True
            # Create rsp buff
            return self.rsp
        # If it isn't print error message and return
        else:
            logging.error("Simulation client hasn't not finished yet with the " + str(self.rqt) +
                          " simulation. Try again later")
            return 0

    def stop(self):
        """Stop the simulation client"""

        # Stop managing loop
        self.mng_stop = True
        self.sim_time = time.time() - self.t_sim_init
        if self.thread and self.thread.is_alive():
            self.thread.join()

    def start(self):
        """Start a simulation client"""

        self.ip_register = Registry.test_register(self.ip_register)
        self.t_sim_init = time.time()
        self.terminated = False
        self.mng_stop = False
        self.thread = Thread(target=self.run)
        self.thread.start()

    def run(self):
        """Run the client loop. Check rqt stack for simulation request. Select the candidate \
        server for simulation. Start simulation."""

        logging.info("Start Client main loop")
        # Continue while not asked for termination or when there are candidates in the list
        # and a server to process them
        while not self.mng_stop:
            if self.rqt:
                # Select a candidate server
                server_hash = self.__select_candidate()

                if server_hash != 0:
                    # We found a server
                    self.server_dispo = True
                    try:
                        self.request_server(server_hash, self.cloud_state[server_hash], self.rqt[-1], "Simulation")
                    except EOFError as eo:
                        # Connection reset by peer
                        logging.error("Unexpected disconnection from the server " +
                                      self.cloud_state[server_hash].address + "\n" + str(eo))
                        time.sleep(5)
                        self.server_dispo = False
                    except Exception as e:
                        raise Exception("Exception during simulation on the server " +
                                        self.cloud_state[server_hash].address + ":" +
                                        str(self.cloud_state[server_hash].port) + "\n" + str(e))
                    if self.server_dispo:
                        # Update the cloud_state list
                        self.mutex_cloud_state.acquire()
                        self.cloud_state[server_hash].nb_threads += 1
                        self.mutex_cloud_state.release()

                        # Clear request from list:
                        self.mutex_rqt.acquire()
                        self.rqt.pop()
                        self.rqt_n -= 1
                        self.mutex_rqt.release()
                else:
                    self.server_dispo = False
                    time.sleep(self.mng_prun_t)
            else:
                time.sleep(self.mng_prun_t)

        self.terminated = True

    def del_clean_simulation(self, server_hash, res):
        """
        Remove a clean simulation result from the result array
        :param server_hash: Int Server id for the cloud
        :param res: rpyc response to process
        """

        if server_hash in self.results:
            server = self.results[server_hash]
            for simulation in server:
                if res == simulation.callback and res.ready:
                    for key, sim_ in enumerate(self.results[server_hash]):
                        if sim_.index == simulation.index:
                            self.mutex_res.acquire()
                            del self.results[server_hash][key]
                            self.mutex_res.release()
                            break
                    break

    def check_sim(self):
        """
        Check if simulations have not timeout or returned errors
        If so, retrieve all the requests of the broken server, add
        them to the request list and update the state of the server
        """

        for server_hash, simulations in self.results.items():
            # For every server, we check its current simulation
            clean = True
            reason = ""
            for simulation in simulations:
                result = simulation.callback
                if result.expired or result.error:
                    reason = "Timeout" if result.expired else "Error"
                    clean = False
                    break
            # If one of the simulation returned an error or a timeout
            if not clean:
                self.mutex_rqt.acquire()
                # Add the request sent to the server to the request list
                for simulation in simulations:
                    simulation.callback = None
                    self.rqt.append(simulation.copy())
                    self.rqt_n += 1
                self.mutex_rqt.release()

                if server_hash in self.cloud_state:
                    self.mutex_cloud_state.acquire()
                    # The server won't be use for simulation anymore.
                    logging.error(reason + " from server: " +
                                  str(self.cloud_state[server_hash].address) + ":" +
                                  str(self.cloud_state[server_hash].port))
                    self.cloud_state[server_hash].status = False
                    self.mutex_cloud_state.release()
                    for connection in self.conn_list:
                        if connection.server_id == server_hash:
                            self.mutex_conn_list.acquire()
                            connection.connexion.close()
                            del connection
                            self.mutex_conn_list.release()
                            break

                self.mutex_res.acquire()
                del self.results[server_hash]
                self.mutex_res.release()

    def request_server(self, server_id, server, rqt, service):
        """Create a connexion to a server and send a request for a service
        Raise Exception if an error occurred."""

        # Connect to the server
        try:
            conn = rpyc.connect(server.address,
                                server.port, config=PROTOCOL_CONFIG)
        except Exception as e:
            exception = "Exception when connecting: " + str(e)
            raise Exception(exception)

        # Create serving thread to handle answer
        try:
            bgt = rpyc.BgServingThread(conn)
        except Exception as e:
            exception = "Exception in serving thread: " + str(e)
            logging.error(exception)
            conn.close()
            raise Exception(exception)

        self.mutex_conn_list.acquire()
        self.conn_list.append(Connexion(server_id, conn, bgt))
        self.mutex_conn_list.release()

        # Create asynchronous handle
        if service in REQUESTS:
            logging.info("Starting " + REQUESTS[service] + " service on server: " +
                         str(server.address) + ":" +
                         str(server.port))
            async_simulation = rpyc.async(eval("conn.root.exposed_" + REQUESTS[service]))
            callback = eval("self.response_" + REQUESTS[service])
        else:
            exception = "Client.request_server: Service unhandled by the client"
            logging.error(exception)
            conn.close()
            bgt._active = False
            raise Exception(exception)

        try:
            res = async_simulation(rqt.rqt)
            res.set_expiry(self.sim_timeout)

            # Assign asynchronous callback
            res.add_callback(callback)
            rqt.callback = res
        except Exception as e:
            exception = "Exception from server: " + str(e)
            logging.error(exception)
            conn.close()
            bgt._active = False
            raise Exception(exception)

        # Add result to the result list to be handled after
        self.mutex_res.acquire()
        if server_id not in self.results:
            self.results[server_id] = []
        self.results[server_id].append(rqt)
        self.mutex_res.release()
