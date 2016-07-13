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

import math


class Fiber:
    """
    Abstract class that describe fiber muscle activity depending its length, velocity, and the current input of the
    motor neurons.
    """

    def __init__(self, h, f_pcsa, length, velocity, f_05):
        """
        Class initialization. Parameters can be found in Tsianos & al. (2012)
        :param h: Float Euler parameter
        :param f_pcsa: Float Fractional Physiological cross-sectional area of the fiber
        :param length: Float Normalized current length of the fiber
        :param velocity: Float normalized current velocity of the fiber
        :param f_05: Float firing rate frequency at which the fiber produce half of its maximal force
        """

        self.h = h

        # Fiber parameters
        self.f_05 = f_05
        self.length = length
        self.max_length = 0.
        self.length_0 = 0.
        self.f_tet = 0.
        self.velocity = velocity
        self.f_pcsa = f_pcsa

        # Frequency recruitment
        self.f_min = 0.5 * self.f_05
        self.f_max = 2.0 * self.f_05
        self.f_env = 0.
        self.u_th = 0.001

        # Firing frequency parameters
        self.t_f1 = 34.3
        self.t_f2 = 22.7
        self.t_f3 = 47.0
        self.t_f4 = 25.2
        self.tf = 0.
        self.f_int = 0.
        self.f_eff = 0.

        # Activation frequency parameters
        self.af = 0.56
        self.n_f0 = 2.1
        self.n_f1 = 5
        self.nf = 0.
        self.activation_frequency = 0.

        # Force-Length parameters
        self.beta = 2.30
        self.omega = 1.12
        self.rho = 1.62

        # Force-Velocity parameters
        self.max_velocity = -7.88
        self.c_v0 = 5.88
        self.c_v1 = 0.
        self.a_v0 = -4.70
        self.a_v1 = 8.41
        self.a_v2 = -5.34
        self.b_v = 0.35

        # Parallel elastic parameters
        self.c1 = 23.
        self.k1 = 0.046
        self.l_r1 = 1.17
        self.eta = 0.01

        # Thick filament compression parameters
        self.c2 = -0.02
        self.k2 = -21.0
        self.l_r2 = 0.70

        # Series elastic element
        self.c_t = 27.8
        self.k_t = 0.0047
        self.l_t = 0.964

        # Initial Energy parameters
        self.e1 = -76.6
        self.e2 = -792
        self.e3 = 124
        self.e4 = 0.72

        # Total Energy parameters
        self.m = 0.25
        self.r = 1.5
        self.a = 0.33
        self.initial_energy = 0.

    def __process_recruitment(self, spike_frequency):
        """
        Update the recruitment of the fiber based on the frequency of the spikes input
        :param spike_frequency: Float frequency of the spiking input
        :return: Float frequency recruitment of the fiber
        """

        self.f_env = self.f_min + (self.f_max - self.f_min) / (
            1 - self.u_th) * spike_frequency if spike_frequency > self.u_th else self.f_min
        return self.f_env

    def __process_tf(self, d_f_eff):
        """
        Process tf value used to process intermediate and effective firing frequencies
        :param d_f_eff: Float derived effective firing frequency
        :return: Float tf value
        """

        self.tf = self.t_f1 * math.pow(self.length, 2) + self.t_f2 * self.f_env if d_f_eff >= 0. \
            else (self.t_f3 + self.t_f4 * self.activation_frequency) / self.length
        return self.tf

    def __intermediate_firing_frequency(self):
        """
        Update intermediate firing frequency which will be used to process effective firing frequency
        :return: Float intermediate firing frequency
        """

        d_f_int = (self.f_env - self.f_int) / self.tf
        self.f_int += self.h * d_f_int
        return self.f_int

    def __effective_firing_frequency(self):
        """
        Update effective firing frequency which will be used to process muscle activity
        :return:  Float effective firing frequency
        """

        d_f_eff = (self.f_int - self.f_eff) / self.tf
        self.f_eff += self.h * d_f_eff
        return self.f_eff

    def __specific_function(self):
        """
        Define the specific function of the fiber that is used to process muscle activity
        :return: Float activation parameter
        """

        return 1.

    def __process_nf(self):
        """
        Update the shape of the sigmoid relationship (nf) based on fiber length
        :return: Float nf parameter
        """

        self.nf = self.n_f0 + self.n_f1 * (1 / self.length - 1)
        return self.nf

    def __activation_frequency(self):
        """
        Update activation frequency which can be used to process active and passive fiber forces
        :return: Float activation frequency of the fiber
        """

        self.activation_frequency = 1 - math.exp(
            - math.pow((self.__specific_function() * self.f_eff / (self.af * self.nf)), self.nf))
        return self.activation_frequency

    def __force_length(self):
        """
        Process the active force based on the current length of the fiber
        :return: Float length based active force of the fiber
        """

        return math.exp(-math.pow(math.fabs((math.pow(self.length, self.beta) - 1) / self.omega), self.rho))

    def __force_velocity(self):
        """
        Process the active force based on the current velocity of the fiber
        :return: Float velocity based active force of the fiber
        """

        if self.velocity <= 0:
            return (self.max_velocity - self.velocity) / \
                   (self.max_velocity + self.velocity * (self.c_v0 + self.c_v1 * self.length))
        else:
            return (self.b_v - self.velocity *
                    (self.a_v0 + self.a_v1 * self.length + self.a_v2 * math.pow(self.length, 2))) / \
                   (self.b_v + self.velocity)

    def __parallel_elastic(self):
        """
        Process the passive force of the parallel elastic part of the fiber
        :return: Float parallel elastic force of the fiber
        """

        return self.c1 * self.k1 * math.log(
            math.exp((self.length / self.max_length - self.l_r1) / self.k1) + 1) + self.eta * self.velocity

    def __thick_filament_compression(self):
        """
        Process the passive force due to the thick filament compression of the fiber
        :return: Float thick filament compression force of the fiber
        """

        return self.c2 * (math.exp(self.k2 * (self.length - self.l_r2)) - 1)

    def __series_elastic(self):
        """
        Process the passive force due to the tendon the fiber
        :return: Float tendon force of the fiber
        """
        return self.c_t * self.k_t * math.log(math.exp((self.length - self.l_t) / self.k_t) + 1)

    def __passive_force(self):
        """
        Update the passive force of the muscle
        :return: Float passive force deployed by the muscle
        """

        return self.__parallel_elastic() + self.activation_frequency * self.__thick_filament_compression()

    def __active_force(self):
        """
        Update the active force of the muscle
        :return: Float active force deployed by the muscle
        """

        return self.__force_length() * self.__force_velocity() * self.activation_frequency

    def __effective_activation(self, force, length):
        return self.activation_frequency

    def __initial_energy(self, force, length, velocity):
        return self.__cross_bridge_energy(force, length, velocity) + self.__activation_energy(force)

    def __initial_tetanic_energy(self, velocity):
        return (self.e1 * math.pow(velocity, 2) + self.e2 * velocity + self.e3) / (self.e4 - velocity)

    def __cross_bridge_energy(self, force, length, velocity):
        return self.__effective_activation(force, length) * self.__force_length() * self.__tetanic_cross_bridge_energy(
            velocity)

    def __tetanic_cross_bridge_energy(self, velocity):
        if velocity <= 0.:
            return self.__initial_tetanic_energy(velocity) - self.__tetanic_activation_energy()
        f_tet_xb_0 = self.__tetanic_cross_bridge_energy(0.)
        return f_tet_xb_0 + self.velocity * (f_tet_xb_0 - self.__tetanic_cross_bridge_energy(-self.h)) / self.h

    def __activation_energy(self, force):
        return self.a / (1 - self.a) * self.__cross_bridge_energy(force, self.length_0, 0.)

    def __tetanic_activation_energy(self):
        return self.a * self.__initial_tetanic_energy(0.)

    def __recovery_energy(self, force, length, velocity):
        return self.__initial_energy(force, length, velocity) * self.r

    def update_force(self, spike_frequency):
        """
        Update the force of the muscle
        :return: Float force deployed by the muscle
        """

        self.__process_recruitment(spike_frequency)
        self.__process_tf((self.f_int - self.f_eff) / self.tf if self.tf != 0 else 0.)
        self.__intermediate_firing_frequency()
        self.__effective_firing_frequency()
        self.__process_nf()
        self.__activation_frequency()

        return self.__passive_force() + self.__active_force()

    def update_energy(self, force, length, energy):
        return (self.__initial_energy(force, length, energy) +
                self.__recovery_energy(force, length, energy)) * self.m


class SlowTwitchFiber(Fiber):
    """
    Describe slow twitch muscle fibers and their activity. Corresponds approximately to Type I muscle fibers
    """

    def __init__(self, h, f_pcsa, length, velocity, f_05):
        """
        Class initialization. Parameters can be found in Tsianos & al. (2012)
        :param h: Float Euler parameter
        :param f_pcsa: Float Fractional Physiological cross-sectional area of the fiber
        :param length: Float Normalized current length of the fiber
        :param velocity: Float normalized current velocity of the fiber
        :param f_05: Float firing rate frequency at which the fiber produce half of its maximal force
        """

        Fiber.__init__(self, h, f_pcsa, length, velocity, f_05)
        # Yielding parameters

        self.c_gamma = 0.35
        self.v_gamma = 0.1
        self.t_gamma = 200  # in ms
        self.yielding = 0.

    def __specific_function(self):
        """
        Process yielding activity of the muscle.
        :return: Float updated yielding
        """

        d_yielding = (1 - self.c_gamma * (1 - math.exp(-self.velocity / self.v_gamma)) - self.yielding) / self.t_gamma
        self.yielding += d_yielding * self.h
        return self.yielding


class FastTwitchFiber(Fiber):
    """
    Describe fast twitch muscle fibers and their activity. Corresponds approximately to Type II muscle fibers
    """

    def __init__(self, h, pcsa, length, velocity, f_05):
        """
        Class initialization. Parameters can be found in Tsianos & al. (2012)
        :param h: Float Euler parameter
        :param pcsa: Float Physiological cross-sectional area of the fiber
        :param length: Float Normalized current length of the fiber
        :param velocity: Float normalized current velocity of the fiber
        :param f_05: Float firing rate frequency at which the fiber produce half of its maximal force
        """

        Fiber.__init__(self, h, pcsa, length, velocity, f_05)
        self.u_r = 0.8
        self.u_th = self.f_pcsa * self.u_r

        # Sag parameters
        self.as1 = 1.76
        self.as2 = 0.96
        self.ts = 43
        self.sag = 0.

        # Firing frequency parameters
        self.t_f1 = 20.6
        self.t_f2 = 13.6
        self.t_f3 = 28.2
        self.t_f4 = 15.1

        # Activation frequency parameters
        self.n_f1 = 3.3

        # Force-Length parameters
        self.beta = 1.55
        self.omega = 0.75
        self.rho = 2.12

        # Force-Velocity parameters
        self.max_velocity = -9.15
        self.c_v0 = -5.70
        self.c_v1 = 9.18
        self.a_v0 = -1.53
        self.a_v1 = 0.
        self.a_v2 = 0.
        self.b_v = 0.69

        # Initial Energy parameters
        self.e1 = 145
        self.e2 = -3322
        self.e3 = 1530
        self.e4 = 1.45

        # Total Energy parameters
        self.r = 1.

    def __specific_function(self):
        """
        Process sag activity of the muscle.
        :return: Float updated sag
        """

        sag_as = self.as1 if self.f_eff < 0.1 else self.as2
        d_sag = (sag_as - self.sag) / self.ts
        self.sag = sag_as + d_sag * self.h
        return self.sag
