# my_supervisor.py
from controller import Supervisor
from supervisor_module import ArenaSupervisor

supervisor = Supervisor()
controller = ArenaSupervisor(supervisor)
timestep = int(supervisor.getBasicTimeStep())

while supervisor.step(timestep) != -1:
    if not controller.check_and_update():
        break

supervisor.simulationSetMode(Supervisor.SIMULATION_MODE_PAUSE)