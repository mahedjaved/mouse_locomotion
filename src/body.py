##
# Mouse Locomotion Simulation
#
# Human Brain Project SP10
#
# This project provides the user with a framework based on Blender allowing:
#  - Edition of a 3D model
#  - Edition of a physical controller model (torque-based or muscle-based)
#  - Edition of a brain controller model (oscillator-based or neural network-based)
#  - Simulation of the model
#  - Optimization of the parameters in distributed cloud simulations
# 
# File created by: Gabriel Urbain <gabriel.urbain@ugent.be>. February 2016
# Modified by: Dimitri Rodarie
##


import math
import logging
from mathutils import Vector as vec
import sys

from brain import Brain
from muscle import *


class Part:
    def __init__(self, config_, simulator, name):
        """Class initialization"""
        self.n_iter = 0
        self.config = config_
        self.logger = config_["logger"]
        self.simulator = simulator
        # Create the muscles objects
        self.muscles = []
        self.muscle_type = config_["muscle_type"] + "(muscle_config, self.simulator)"
        self.name = name

class Leg(Part):
    """This class represents a generic leg and its current behaviour in the control process"""

    def __init__(self, config_, orien_, simulator, name):
        """Class initialization"""
        Part.__init__(self, config_, simulator, name)
        self.orien = orien_
        # Create the muscles objects
        for muscle_config in config_["muscles"]:
            self.muscles.append(eval(self.muscle_type))
        self.connection_matrix = config_["connection_matrix"]

    def get_power(self):
        """Return the time-step power developed by all the leg muscles"""

        power = 0
        for m in self.muscles:
            power += m.get_power()

        return power

    def update(self, brain_output):
        """Update control signals and forces"""
        for i in range(len(self.muscles)):
            # Assertion
            if len(self.connection_matrix[self.muscles[i].name]) != len(brain_output):
                self.logger.error("The brain outputs number (" + len(brain_output) +
                    ") should match the number in the connection matrix (" +
                    len(self.connection_matrix[self.muscles[i].name]) + "). Please verify config!")
            # Send linear combination of brain outputs
            else:
                ctrl_sig = 0
                j = 0
                for output in brain_output:
                    ctrl_sig += self.connection_matrix[self.muscles[i].name][j] * output
                    j += 1

                self.muscles[i].update(ctrl_sig=ctrl_sig)

                self.n_iter += 1
                self.logger.debug(self.name + " " + self.orien + " iteration " + str(self.n_iter) + ": Control signal = " +
                                  str(ctrl_sig))


class Backleg(Leg):
    """This class represents a generic backleg and its current behaviour in the control process"""

    def __init__(self, config_, orien_, simulator):
        """Class initialization"""
        config = {"logger": config_.logger,
                  "muscle_type": config_.muscle_type,
                  "connection_matrix": config_.connection_matrix}
        if orien_ == "L":
            config["muscles"] = config_.back_leg_L_muscles
        else:
            config["muscles"] = config_.back_leg_R_muscles
        Leg.__init__(self, config, orien_, simulator, type(self).__name__)


class Foreleg(Leg):
    """This class represents a generic foreleg and its current behaviour in the control process"""

    def __init__(self, config_, orien_, simulator):
        """Class initialization"""
        config = {"logger": config_.logger,
                  "muscle_type": config_.muscle_type,
                  "connection_matrix": config_.connection_matrix}
        if orien_ == "L":
            config["muscles"] = config_.front_leg_L_muscles
        else:
            config["muscles"] = config_.front_leg_R_muscles
        Leg.__init__(self, config, orien_, simulator, type(self).__name__)


class Body(Part):
    """This class represents the mouse body and its current behaviour in the control process"""

    def __init__(self, config_, simulator):
        """Class initialization"""
        Part.__init__(self,
                      {"logger": config_.logger, "muscle_type": config_.muscle_type},
                      simulator,
                      config_.body["name"])
        self.config = config_
        # Get body object
        self.body_obj = self.simulator.get_object(config_.body["obj"])
        if self.body_obj is None:
            self.logger.error("Body " + self.name + " doesn't exit. Check your configuration file!")
            self.active = False

        # Create and init variables for loss function
        self.origin = self.body_obj.worldTransform * vec((0, 0, 0))
        self.position = self.origin
        self.dist = vec(self.position - self.origin).length
        self.powers = []
        self.av_power = 0.0
        self.loss_fct = 0.0

        # Create 4 legs
        self.l_fo_leg = Foreleg(config_, "L", simulator)
        self.r_fo_leg = Foreleg(config_, "R", simulator)
        self.l_ba_leg = Backleg(config_, "L", simulator)
        self.r_ba_leg = Backleg(config_, "R", simulator)

        # Create the brain object
        self.brain = Brain(config_)

        # Create the muscles objects following config
        for muscle_config in config_.body["muscles"]:
            self.muscles.append(eval(self.muscle_type))

    def compute_traveled_dist(self):
        """Return a float representing the distance between origin and the current position"""

        # Get current position
        self.position = self.body_obj.worldTransform * vec((0, 0, 0))

        # Get distance
        self.dist = vec(self.position - self.origin).length

        return

    def compute_power(self):
        """Compute time-step power at each iteration"""

        power = 0.0

        # Get power from legs
        power += self.l_ba_leg.get_power()
        power += self.r_ba_leg.get_power()
        power += self.l_fo_leg.get_power()
        power += self.r_fo_leg.get_power()

        # Get power from body muscles
        for m in self.muscles:
            power += m.get_power()

        # Append to powers list
        self.powers.append(power)

        return

    def get_loss_fct(self):
        """Compute the body loss function. This should be called only at the end of the simulation
        in order to avoid useless computation at each iteration"""

        self.compute_traveled_dist()
        self.av_power = sum(self.powers) / float(len(self.powers))

        self.loss_fct = math.tanh(self.dist / self.config.dist_ref) * \
            math.tanh(self.config.power_ref / self.av_power)

        return self.loss_fct

    def update(self):
        """Update control signals and forces"""

        # Update brain
        self.brain.update()
        brain_output = [float(self.brain.state[0]), float(self.brain.state[1]), float(self.brain.state[2]),
                    float(self.brain.state[3])]

        # Update the four legs
        self.l_ba_leg.update(brain_output)
        self.r_ba_leg.update(brain_output)
        self.l_fo_leg.update(brain_output)
        self.r_fo_leg.update(brain_output)

        # Update other muscles
        for muscle in self.muscles:
            muscle.update()

        # Update powers list
        self.compute_power()

        self.n_iter += 1
        self.logger.debug("Body " + self.name + " iteration " + str(self.n_iter))
        self.logger.debug("Average power: " + "{0:0.2f}".format(self.av_power))
