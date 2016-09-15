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
# File created by: Gabriel Urbain <gabriel.urbain@ugent.be>
#                  Dimitri Rodarie <d.rodarie@gmail.com>
# May 2016
##

import copy
import bge
from .simulatorUtils import SimulatorUtils


class BlenderUtils(SimulatorUtils):
    def __init__(self, scene):
        self.scene = scene

    def get_time_scale(self):
        return bge.logic.getLogicTicRate()

    def draw_line(self, point1, point2, color):
        bge.render.drawLine(point1, point2, color)

    def exists_Object(self, name):
        return name in self.scene.objects

    def get_object(self, name):
        if self.exists_Object(name):
            return self.scene.objects[name]
        return None

    def get_orientation(self, name):
        obj = self.get_object(name)
        if obj is not None:
            return copy.copy(obj.worldOrientation.to_euler())
        return None