# coding=utf-8
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
# July 2016
##

from muscles import Muscle, SlowTwitchFiber, FastTwitchFiber
import numpy as np


class BrownMuscle(Muscle):
    def __init__(self, params_, simulator):
        """
        Class initialization. \
        Mammalian Muscle Model for predicting force and energetics during physiological behavior
        Based on BROWN, CHENG and LOEB muscle models

        :param params_: Dictionary containing parameter for the muscle
        :param simulator: SimulatorUtils class to access utility functions
        """

        Muscle.__init__(self, params_, simulator)
        # Euler parameter
        self.h = 0.01 if "h" not in self.params else self.params["h"]

        # Fiber type architecture of the muscle
        self.percent_slow_fiber = self.params["percent_slow_fiber"] if "percent_slow_fiber" in self.params else 3.5

        # Activation Frequency at which the muscle produce half of its max_force
        self.f_05 = 0.36  # The cycle frequency ranged from 0.15 to 0.72 Hz for the mouse (Guisheng Zhong, 2011)
        self.pcsa = 0. if "pcsa" not in self.params else self.params["pcsa"]

        self.l_ce = np.linalg.norm(self.app_point_1 - self.app_point_2)
        # Length at optimal fascicle
        self.l_0 = self.l_ce if "l_0" not in self.params else self.params["l_0"]
        # Tendon Length
        self.l_se = 0. if "l_se" not in self.params else self.params["l_se"]
        self.l_max = 1.5 * self.l_ce if "max_length" not in self.params else self.params["max_length"]
        self.angle = 0. if "angle" not in self.params else self.params["angle"]

        self.v_ce = 0.

        self.fibers = {
            SlowTwitchFiber(self.h, self.pcsa, self.l_ce, self.v_ce,
                            self.f_05, self.l_se, self.l_max, self.l_0): self.percent_slow_fiber,
            FastTwitchFiber(self.h, self.pcsa, self.l_ce, self.v_ce,
                            self.f_05, self.l_se, self.l_max, self.l_0): 100. - self.percent_slow_fiber}
        self.last_signal = 0.
        self.start_period = 0.
        self.current_time = 0.
        self.current_force = 0.

    def update_contractile_element(self):
        l_se = 0.
        for fiber, percent in self.fibers.items():
            l_se += fiber.get_length_elastic(self.current_force) * percent
        self.l_se = l_se / len(self.fibers) if len(self.fibers) > 0 else 0.

        # get length and velocity
        self.app_point_1_world = self.obj1.worldTransform * self.app_point_1
        self.app_point_2_world = self.obj2.worldTransform * self.app_point_2
        l = np.linalg.norm(self.app_point_2_world - self.app_point_1_world)
        old_l_ce = self.l_ce
        # self.l_ce = (l - l_se) / (self.angle * self.l_0) if self.l_0 > 0 and self.angle != 0. else self.l_0
        self.l_ce = l
        self.v_ce = (self.l_ce - old_l_ce) / (self.h * self.l_0)

    def update(self, **kwargs):
        if "ctrl_sig" in kwargs:
            ctrl_sig = kwargs["ctrl_sig"]
        else:
            ctrl_sig = None
        force = 0.
        for fiber, percent in self.fibers.items():
            force += fiber.update_force(ctrl_sig, self.l_ce, self.v_ce) * percent
        self.current_force = force
        self.update_contractile_element()
        return force

    def get_power(self):
        energy = 0.
        for fiber, percent in self.fibers.items():
            energy += fiber.update_energy(self.current_force) * percent
        return energy

    def print_update(self):
        print("-------------------------------------------------------------------------\n" +
              "Update " + str(self.n_iter) + " Muscle " + self.name + ":\n" +
              "Length: " + str(self.l_ce) + "\n" +
              "Velocity: " + str(self.v_ce) + "\n" +
              "Fibers: \n")
        for fiber in self.fibers:
            fiber.print_updates()
        print("Force: " + str(self.current_force) + "\n" +
              "-------------------------------------------------------------------------\n")
