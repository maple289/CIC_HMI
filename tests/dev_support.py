"""Explicit simulator harness for tests; never packaged in the operator app."""
import copy
from prevex_hmi.devices.configuration import load_settings as _load
from prevex_hmi.gui.window import MainWindow as OperatorWindow
from prevex_hmi.gui.worker import MonitoringWorker as OperatorWorker


def load_settings(path):return _load(path,allow_simulation=True)


class MainWindow(OperatorWindow):
    def __init__(self,*args,**kwargs):
        kwargs['simulation_authorized']=True
        super().__init__(*args,**kwargs)

    def save_connection_inputs(self):
        # Production forms save hardware preferences. Restore only the explicit
        # test transport after exercising the same form/persistence workflow.
        simulated=self.settings['mode']=='simulation'
        result=super().save_connection_inputs()
        if simulated:
            self.settings['mode']='simulation'
            selection=self.settings['analyzer_selection']
            if selection!='Auto Detect':self.settings['simulated_family']=selection
            self.refresh_connection_labels()
        return result


class MonitoringWorker(OperatorWorker):
    def __init__(self,*args,**kwargs):
        kwargs['simulation_authorized']=True
        super().__init__(*args,**kwargs)
