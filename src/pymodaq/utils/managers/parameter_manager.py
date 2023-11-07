from pathlib import Path
from typing import List, Union, Dict

from qtpy import QtWidgets, QtCore
from pymodaq.utils.managers.action_manager import ActionManager
from pymodaq.utils.parameter import Parameter, ParameterTree, ioxml
from pymodaq.utils.gui_utils.file_io import select_file
from pymodaq.utils.config import get_set_config_dir


class ParameterTreeWidget(ActionManager):

    def __init__(self):
        super().__init__()

        self.widget = QtWidgets.QWidget()
        self.widget.setLayout(QtWidgets.QVBoxLayout())

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.widget.layout().addWidget(self.splitter)
        self.widget.layout().setContentsMargins(0, 0, 0, 0)

        toolbar = QtWidgets.QToolBar()
        self.set_toolbar(toolbar)
        self.tree: ParameterTree = ParameterTree()

        self.widget.header = self.tree.header  # for backcompatibility

        self.tree.setMinimumWidth(150)
        self.tree.setMinimumHeight(300)

        self.splitter.addWidget(toolbar)
        self.splitter.addWidget(self.tree)

        self.splitter.setSizes([0, 300])
        self.setup_actions()

    def setup_actions(self):
        """

        See Also
        --------
        ActionManager.add_action
        """
        self.add_action('save_settings', 'Save Settings', 'saveTree', "Save Settings")
        self.add_action('load_settings', 'Load Settings', 'openTree', "Load Settings")


class ParameterManager:
    """Class dealing with Parameter and ParameterTree

    Attributes
    ----------
    params: list of dicts
        Defining the Parameter tree like structure
    settings_name: str
        The particular name to give to the object parent Parameter (self.settings)
    settings: Parameter
        The higher level (parent) Parameter
    settings_tree: QWidget
        widget Holding a ParameterTree and a toolbar for interacting with the tree
    tree: ParameterTree
        the underlying ParameterTree
    """
    settings_name = 'custom_settings'
    params = []

    def __init__(self, settings_name: str = None):
        if settings_name is None:
            settings_name = self.settings_name
        # create a settings tree to be shown eventually in a dock
        # object containing the settings defined in the preamble
        # create a settings tree to be shown eventually in a dock
        self._settings_tree = ParameterTreeWidget()

        self._settings_tree.get_action('save_settings').connect_to(self.save_settings)
        self._settings_tree.get_action('load_settings').connect_to(self.update_settings)

        self.settings: Parameter = Parameter.create(name=settings_name, type='group', children=self.params)  # create a Parameter
        # object containing the settings defined in the preamble

    @property
    def settings_tree(self):
        return self._settings_tree.widget

    @property
    def tree(self):
        return self._settings_tree.tree

    @property
    def settings(self):
        return self._settings

    @settings.setter
    def settings(self, settings: Union[Parameter, List[Dict[str, str]], Path]):
        settings = self.create_parameter(settings)
        self._settings = settings
        self.tree.setParameters(self._settings, showTop=False)  # load the tree with this parameter object
        self._settings.sigTreeStateChanged.connect(self.parameter_tree_changed)

    @staticmethod
    def create_parameter(settings: Union[Parameter, List[Dict[str, str]], Path]) -> Parameter:

        if isinstance(settings, List):
            _settings = Parameter.create(title='Settings', name='settings', type='group', children=settings)
        elif isinstance(settings, Path) or isinstance(settings, str):
            settings = Path(settings)
            _settings = Parameter.create(title='Settings', name='settings',
                                        type='group', children=ioxml.XML_file_to_parameter(str(settings)))
        elif isinstance(settings, Parameter):
            _settings = Parameter.create(title='Settings', name=settings.name(), type='group')
            _settings.restoreState(settings.saveState())
        else:
            raise TypeError(f'Cannot create Parameter object from {settings}')
        return _settings

    def parameter_tree_changed(self, param, changes):
        for param, change, data in changes:
            path = self._settings.childPath(param)
            if change == 'childAdded':
                self.child_added(param, data)

            elif change == 'value':
                self.value_changed(param)

            elif change == 'parent':
                self.param_deleted(param)

    def value_changed(self, param):
        """Non-mandatory method  to be subclassed for actions to perform (methods to call) when one of the param's
        value in self._settings is changed

        Parameters
        ----------
        param: Parameter
            the parameter whose value just changed

        Examples
        --------
        >>> if param.name() == 'do_something':
        >>>     if param.value():
        >>>         print('Do something')
        >>>         self.settings.child('main_settings', 'something_done').setValue(False)
        """
        ...

    def child_added(self, param, data):
        """Non-mandatory method to be subclassed for actions to perform when a param  has been added in self.settings

        Parameters
        ----------
        param: Parameter
            the parameter where child will be added
        data: Parameter
            the child parameter
        """
        pass

    def param_deleted(self, param):
        """Non-mandatory method to be subclassed for actions to perform when one of the param in self.settings has been deleted

        Parameters
        ----------
        param: Parameter
            the parameter that has been deleted
        """
        pass

    def save_settings(self, ):
        """ Method to save the current settings using a xml file extension.

        The starting directory is the user config folder with a subfolder called settings folder
        """
        file_path = select_file(get_set_config_dir('settings', user=True), save=True, ext='xml', filter='*.xml',
                               force_save_extension=True)
        if file_path:
            ioxml.parameter_to_xml_file(self.settings, file_path.resolve())

    def load_settings(self):
        """ Method to load settings into the parameter using a xml file extension.

        The starting directory is the user config folder with a subfolder called settings folder
        """
        file_path = select_file(get_set_config_dir('settings', user=True), save=False, ext='xml', filter='*.xml',
                                force_save_extension=True)
        if file_path:
            self.settings = self.create_parameter(file_path.resolve())

    def update_settings(self):
        """ Method to update settings using a xml file extension.

        The file should define the same settings structure (names and children)

        The starting directory is the user config folder with a subfolder called settings folder
        """
        file_path = select_file(get_set_config_dir('settings', user=True), save=False, ext='xml', filter='*.xml',
                                force_save_extension=True)
        if file_path:
            _settings = self.create_parameter(file_path.resolve())
            #TODO: use a Parameter comparison to check if one can refresh the current settings
            if True:  # here will be the comparison
                self.settings.restoreState(_settings.saveState())


if __name__ == '__main__':

    class RealParameterManager(ParameterManager):
        params = {'title': 'Numbers:', 'name': 'numbers', 'type': 'group', 'children': [
            {'title': 'Standard float', 'name': 'afloat', 'type': 'float', 'value': 20., 'min': 1.,
             'tip': 'displays this text as a tooltip'},
            {'title': 'Linear Slide float', 'name': 'linearslidefloat', 'type': 'slide', 'value': 50, 'default': 50,
             'min': 0,
             'max': 123, 'subtype': 'linear'},
            {'title': 'Log Slide float', 'name': 'logslidefloat', 'type': 'slide', 'value': 50, 'default': 50,
             'min': 1e-5,
             'max': 1e5, 'subtype': 'log'},
        ]},


    import sys
    from qtpy import QtWidgets
    app = QtWidgets.QApplication(sys.argv)
    param_manager = RealParameterManager()
    param_manager.settings_tree.show()
    sys.exit(app.exec())

