import math
import random
import subprocess

import numpy as np
import os

import time

import copy

import multiprocessing

IN_TO_MM = 25.4

class Simulation:
    def __init__(self, depth=1):
        self.commands = ["newdocument(0)", f"mi_probdef(0, \"millimeters\", \"planar\", 1E-8, {depth})"]
        self.commands += ['mi_addboundprop("dirichlet", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)']

        self.points = {}
        self.materials = {}
        self.circuits = 0
        self.boundaries = 0

    def run_sim(self, id):
        self.commands += [f"mi_saveas(\"sim_data\\\\Untitled{id}.fem\")", "mi_analyse(1)", "mi_loadsolution()"]

    def save(self, varname, id):
        self.commands += [f"f = openfile(\"sim_data\\\\femmoutfile{id}\", \"a+\")", f"write(f, {varname})", 'write(f, "\\n")', 'flush()', 'closefile(f)']

    def calculate_force(self, blocks, id):
        self.commands += ['mo_hidedensityplot()']
        self.commands += ['mo_hidecontourplot()']
        self.commands += ['mo_seteditmode("area")']

        for i in blocks:
            self.commands += [f"mo_selectblock({i[0]}, {i[1]})"]
        # self.commands += ["pause()"]

        self.commands += ['force = mo_blockintegral(18)', 'mo_close()']
        self.save("force", id)

    def zoom_useful(self):
        x = []
        y = []
        for k, v in self.points.items():
            x.append(k[0])
            y.append(k[1])

        self.commands += [f"mo_zoom({min(x)}, {min(y)}, {max(x)}, {max(y)})"]
        self.commands += ['mo_showdensityplot(1,0,2,0,"bmag")']
        self.commands += ['mo_showcontourplot(19,-0.01,0.01,real)']

    def take_cap(self, n, id):
        self.commands += [f"mo_savebitmap(\"sim_data\\\\id{id}n{n}.bmp\")"]

    def move_group(self, group, x, y):
        self.commands += ["mi_clearselected()"]
        # self.commands += ["pause()"]
        self.commands += [f"mi_selectgroup({group})"]
        # self.commands += ["pause()"]
        self.commands += [f"mi_movetranslate({x}, {y}, 4)"]
        # self.commands += ["pause()"]
        self.commands += ["mi_clearselected()"]

    def add_point(self, x, y, group=0):
        if (x, y) not in self.points:
            self.commands += [f"mi_addnode({x}, {y})"]
            self.points[(x, y)] = 0

    def draw_line(self, x1, y1, x2, y2, group=0, propname=""):
        self.add_point(x1, y1)
        self.add_point(x2, y2)

        self.commands += [f"mi_addsegment({x1}, {y1}, {x2}, {y2})"]
        self.commands += [f"mi_selectsegment({(x1 + x2) / 2}, {(y1 + y2) / 2})"]
        self.commands += [f"mi_setsegmentprop(\"{propname}\", 0, 0, 0, {group})"]
        self.commands += ["mi_clearselected()"]

    def rect_with_mat(self, x1, y1, x2, y2, name, mag_angle=0, current=0, group=0):
        self.draw_contour(0, 0, [
            (x1, y1),
            (x1, y2),
            (x2, y2),
            (x2, y1),
        ], group=group)

        self.set_materials((x1 + x2) / 2, (y1 + y2) / 2, name, mag_angle, current)

    def draw_contour(self, x, y, l, group=0):
        for iind, i in enumerate(l):
            j = l[iind - 1]

            self.draw_line(x + i[0], y + i[1], x + j[0], y + j[1], group=group)

    def create_boundaries(self):
        x = []
        y = []
        for k, v in self.points.items():
            x.append(k[0])
            y.append(k[1])

        x_center = (max(x) - min(x)) / 2 + min(x)
        y_center = (max(y) - min(y)) / 2 + min(y)

        r = max(max(x) - min(x), max(y) - min(y))

        self.commands += [f"mi_makeABC(7, {r}, {x_center}, {y_center}, {0})"]

    def create_apb(self, x1, y1, x2, y2, x3, y3, x4, y4, group=0):
        self.boundaries += 1

        self.commands += [f"mi_addboundprop(\"apb{self.boundaries}\", 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0)"]

        self.draw_line(x1, y1, x2, y2, propname=f"apb{self.boundaries}", group=group)
        self.draw_line(x3, y3, x4, y4, propname=f"apb{self.boundaries}", group=group)

    def create_dirichlet_line(self, x1, y1, x2, y2, group=0):
        self.draw_line(x1, y1, x2, y2, propname=f"dirichlet{self.boundaries}", group=group)

    def add_materials(self, name):
        if name not in self.materials:
            self.materials[name] = 0
            self.commands += [f"mi_getmaterial(\"{name}\")"]

    def set_materials(self, x, y, name, mag_angle=0, current=0, group=0):
        self.add_materials(name)

        current_str = ""
        if current != 0:
            self.circuits += 1
            self.commands += [f"mi_addcircprop(\"circuit{self.circuits}\", {current}, 1)"]
            current_str = "circuit" + str(self.circuits)

        self.commands += ["mi_clearselected()"]
        self.commands += [f"mi_addblocklabel({x}, {y})"]
        self.commands += [f"mi_selectlabel({x}, {y})"]
        self.commands += [f"mi_setblockprop(\"{name}\", 1, 0, \"{current_str}\", {mag_angle}, {group}, 1)"]
        self.commands += ["mi_clearselected()"]

    def output(self):
        return "\n\r".join(self.commands)

    def quit(self):
        self.commands += ["quit()"]


class Motor:
    def __init__(self, id, current=20, hallbeck=2):
        self.phases = 3
        self.pole_pitch = 0.25 * IN_TO_MM # mm
        self.phase_pitch = self.pole_pitch * 2 / self.phases

        self.power_density = 0.1  # w/cm^2

        self.pcb_thickness = 1.6 # mm
        self.copper_thickness = 0.035  # in mm -> 2 oz
        self.copper_spacing = 0.2 # mm
        self.air_gap = 0.5

        self.back_iron_thickness = 3 # mm
        self.magnet_thickness = 0.125 * IN_TO_MM # mm
        self.magnet_spacing = 0
        self.depth = 0.5 * IN_TO_MM # mm

        self.sim = Simulation(depth=self.depth)

        self.id = id
        self.current = current
        self.hallbeck = hallbeck
        self.magnet_width = self.pole_pitch / self.hallbeck

    def draw_wire(self, x, current_mul):
        width = self.phase_pitch - self.copper_spacing
        resistivity = 1.68e-8  # ohm m
        csa = self.copper_thickness * width * 1e-6  # m^2

        resistance = resistivity / csa  # ohm / m
        allowed_power_dissipation = self.phase_pitch * 10 * self.power_density  # watts / m
        current = self.current/2

        self.sim.rect_with_mat(x - width / 2, self.pcb_thickness / 2, x + width / 2, (self.pcb_thickness / 2) + self.copper_thickness,
                               "Copper", group=1, current=current_mul * current)

        self.sim.rect_with_mat(x - width / 2, -self.pcb_thickness / 2, x + width / 2, -(self.pcb_thickness / 2) - self.copper_thickness,
                               "Copper", group=1, current=current_mul * current)

    def build(self, x, copies=1):
        if copies > 2:
            # then offset x by one whole pole pitch
            x += self.pole_pitch

        magnet_end_y = self.pcb_thickness / 2 + self.air_gap + self.magnet_thickness
        
        angle = 0
        for i in range(copies * self.hallbeck):
            angle += 180 / self.hallbeck
            if angle == 360:
                angle = 0
            self.sim.rect_with_mat(self.magnet_spacing / 2 + i * self.magnet_width,
                                self.pcb_thickness / 2 + self.air_gap,
                                self.magnet_width * (i + 1) - self.magnet_spacing / 2,
                                magnet_end_y,
                                "N40", mag_angle=90 + angle)

            self.sim.rect_with_mat(self.magnet_spacing / 2 + i * self.magnet_width,
                                - self.pcb_thickness / 2 - self.air_gap,
                                self.magnet_width * (i + 1) - self.magnet_spacing / 2,
                                - magnet_end_y,
                                "N40", mag_angle=90 + angle)

        backiron_end_y = magnet_end_y + self.back_iron_thickness

        self.sim.rect_with_mat(0, magnet_end_y, self.pole_pitch * copies, backiron_end_y, "1018 Steel")
        self.sim.rect_with_mat(0, -magnet_end_y, self.pole_pitch * copies, -backiron_end_y, "1018 Steel")

        airgap_end = self.pcb_thickness / 2 + self.air_gap


        # top stator
        self.sim.create_apb(0, backiron_end_y + 5, 0, backiron_end_y, self.pole_pitch * copies, backiron_end_y + 5, self.pole_pitch * copies, backiron_end_y)
        self.sim.create_apb(0, backiron_end_y, 0, magnet_end_y, self.pole_pitch * copies, backiron_end_y, self.pole_pitch * copies, magnet_end_y)
        self.sim.create_apb(0, magnet_end_y, 0, airgap_end, self.pole_pitch * copies, magnet_end_y, self.pole_pitch * copies, airgap_end)

        # bottom stator
        self.sim.create_apb(0, -backiron_end_y - 5, 0, -backiron_end_y, self.pole_pitch * copies, -backiron_end_y - 5, self.pole_pitch * copies, -backiron_end_y)
        self.sim.create_apb(0, -backiron_end_y, 0, -magnet_end_y, self.pole_pitch * copies, -backiron_end_y, self.pole_pitch * copies, -magnet_end_y)
        self.sim.create_apb(0, -magnet_end_y, 0, -airgap_end, self.pole_pitch * copies, -magnet_end_y, self.pole_pitch * copies, -airgap_end)


        self.sim.create_dirichlet_line(0, backiron_end_y + 5, self.pole_pitch * copies, backiron_end_y + 5)
        self.sim.create_dirichlet_line(0, -backiron_end_y - 5, self.pole_pitch * copies, -backiron_end_y - 5)

        airgap_start = self.pcb_thickness / 2 + self.copper_thickness

        # middle stator
        self.sim.create_apb(0, airgap_start, 0, -airgap_start, self.pole_pitch * copies, airgap_start, self.pole_pitch * copies, -airgap_start)
        self.sim.create_apb(0, airgap_start, 0, airgap_end, self.pole_pitch * copies, airgap_start, self.pole_pitch * copies, airgap_end)
        self.sim.create_apb(0, -airgap_start, 0, -airgap_end, self.pole_pitch * copies, -airgap_start, self.pole_pitch * copies, -airgap_end)

        self.sim.set_materials(x + self.pole_pitch / 2, 0, "Air")
        self.sim.set_materials(self.pole_pitch / 2, backiron_end_y + 2.5, "Air")
        self.sim.set_materials(self.pole_pitch / 2, -backiron_end_y - 2.5, "Air")

        electrical_angle = x/(self.pole_pitch * 2) * 2 * math.pi
        electrical_angle = electrical_angle % (2 * math.pi)
        print_str = f"{x:.3f} {(np.rad2deg(electrical_angle)):6.1f} deg Phase currents: "
        wire_mid = (self.pcb_thickness + self.copper_thickness) / 2
        force_blocks = []
        for i in range(self.phases):
            wire_x = x + i * self.phase_pitch
            current = self.current * math.sin(electrical_angle + 2 * math.pi / 3 * i)
            print_str += f"{['A', 'B', 'C'][i]}: {current:.3f}A\t"
            self.draw_wire(wire_x, current)
            force_blocks += [(wire_x, wire_mid),
                             (wire_x, -wire_mid)]
        print(print_str)

        self.sim.run_sim(self.id)
        self.sim.zoom_useful()
        self.sim.take_cap(0, self.id)


        self.sim.calculate_force(force_blocks, self.id)

        self.sim.quit()
        open(f"sim_data\sim{self.id}.lua", mode="w+").write(self.sim.output())

    def run(self):

        a = subprocess.Popen(["C:\\femm42\\bin\\femm.exe", f"-lua-script=E:\dev\linear-actuator-hardware\sim_data\sim{self.id}.lua"])
        return a

    def analyze(self):
        torques = []

        for line in open(f"sim_data\\femmoutfile{self.id}", mode="r+").readlines():
            torques.append(abs(float(line.strip())))

        # os.remove(f"femmoutfile{self.id}")
        os.remove(f"sim_data\\Untitled{self.id}.fem")
        os.remove(f"sim_data\\sim{self.id}.lua")
        os.remove(f"sim_data\\Untitled{self.id}.ans")

        return torques


if __name__ == '__main__':

    for i in range(10):
        m = Motor(f"test{i:03}", current=20, hallbeck=2)
        m.build(i * 0.1, 4)
        m.run()
        time.sleep(1)
    # m.analyze()
