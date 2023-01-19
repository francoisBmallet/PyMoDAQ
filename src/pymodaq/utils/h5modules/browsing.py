# -*- coding: utf-8 -*-
"""
Created the 15/11/2022

@author: Sebastien Weber
"""
import os
from collections import OrderedDict
from typing import List
import warnings
import logging
import webbrowser
import numpy as np
from pathlib import Path
from packaging import version as version_mod

from pymodaq.utils.logger import set_logger, get_module_name
from pymodaq.utils.config import Config
from qtpy import QtGui, QtCore
from qtpy.QtCore import Qt, QObject, Signal, QByteArray

import pymodaq.utils.parameter.ioxml

from pymodaq.utils.tree_layout.tree_layout_main import TreeLayout
from pymodaq.utils.daq_utils import capitalize
from pymodaq.utils.data import Axis
from pymodaq.utils.gui_utils.utils import h5tree_to_QTree, pngbinary2Qlabel
from pymodaq.utils.gui_utils.file_io import select_file
from pymodaq.utils.plotting.data_viewers.viewerND import ViewerND
from qtpy import QtWidgets
from pymodaq.utils import daq_utils as utils
from pymodaq.utils.managers.action_manager import ActionManager
from pymodaq.utils.managers.parameter_manager import ParameterManager
from pymodaq.utils.messenger import messagebox
from .backends import H5Backend
from . import data_saving
from .utils import find_scan_node

config = Config()
logger = set_logger(get_module_name(__file__))


class H5BrowserUtil(H5Backend):
    """Utility object to interact and get info and data from a hdf5 file

    Inherits H5Backend and all its functionalities

    Parameters
    ----------
    backend: str
        The used hdf5 backend: either tables, h5py or h5pyd
    """
    def __init__(self, backend='tables'):
        super().__init__(backend=backend)

    def export_data(self, node_path='/', filesavename='datafile.h5'):
        """Export data in nodes in another file format

        Parameters
        ----------
        node_path: str
            the path in the file
        filesavename:
            the exported file name with a particular extension
            Accepted extensions are:
            * txt: to save node content in a tab delimited text file
            * ascii: to save node content in a tab delimited ascii file
            * h5
        """
        if filesavename != '':
            file = Path(filesavename)
            node = self.get_node(node_path)
            if file.suffix == '.txt' or file.suffix == '.ascii':
                if 'ARRAY' in node.attrs['CLASS']:
                    data = node.read()
                    if not isinstance(data, np.ndarray):
                        # in case one has a list of same objects (array of strings for instance, logger or other)
                        data = np.array(data)
                        np.savetxt(filesavename,
                                   data if file.suffix == '.txt' else data.T if len(data.shape) > 1 else [data],
                                   '%s', '\t')
                    else:
                        np.savetxt(filesavename,
                                   data if file.suffix == '.txt' else data.T if len(data.shape) > 1 else [data],
                                   '%.6e', '\t')

                elif 'GROUP' in node.attrs['CLASS']:
                    data_tot = []
                    header = []
                    dtypes = []
                    fmts = []
                    for subnode_name, subnode in node.children().items():
                        if 'ARRAY' in subnode.attrs['CLASS']:
                            if len(subnode.attrs['shape']) == 1:
                                data = subnode.read()
                                if not isinstance(data, np.ndarray):
                                    # in case one has a list of same objects (array of strings for instance, logger or other)
                                    data = np.array(data)
                                data_tot.append(data)
                                dtypes.append((subnode_name, data.dtype))
                                header.append(subnode_name)
                                if data.dtype.char == 'U':
                                    fmt = '%s'  # for strings
                                elif data.dtype.char == 'l':
                                    fmt = '%d'  # for integers
                                else:
                                    fmt = '%.6f'  # for decimal numbers
                                fmts.append(fmt)

                    data_trans = np.array(list(zip(*data_tot)), dtype=dtypes)
                    np.savetxt(filesavename, data_trans, fmts, '\t', header='#' + '\t'.join(header))
            elif file.suffix == '.h5':
                self.save_file_as(str(file))
                copied_file = H5Backend()
                copied_file.open_file(str(file), 'a')

                copied_file.h5file.move_node(self.get_node_path(node), newparent=copied_file.h5file.get_node('/'))
                copied_file.h5file.remove_node('/Raw_datas', recursive=True)
                copied_file.close_file()

    def get_h5file_scans(self, where='/'):
        """Get the list of the scan nodes in the file

        Parameters
        ----------
        where: str
            the path in the file

        Returns
        -------
        list of dict
            dict with keys: scan_name, path (within the file) and data (the live scan png image)
        """
        # TODO add a test for this method
        scan_list = []
        where = self.get_node(where)
        for node in self.walk_nodes(where):
            if 'pixmap2D' in node.attrs:
                scan_list.append(
                    dict(scan_name='{:s}_{:s}'.format(node.parent_node.name, node.name), path=node.path,
                         data=node.attrs['pixmap2D']))

        return scan_list

    def get_h5_attributes(self, node_path):
        """Get the list of attributes (metadata) of a given node

        Parameters
        ----------
        node_path: str
            the path in the file

        Returns
        -------
        attr_dict: OrderedDict
            attributes as a dict
        settings: str
            settings attribute
        scan_settings: str
            scan settings attribute
        pixmaps: list of pixmap
        """
        node = self.get_node(node_path)
        attrs_names = node.attrs.attrs_name
        attr_dict = OrderedDict([])
        for attr in attrs_names:
            # if attr!='settings':
            attr_dict[attr] = node.attrs[attr]

        settings = None
        scan_settings = None
        if 'settings' in attrs_names:
            if node.attrs['settings'] != '':
                settings = node.attrs['settings']

        if 'scan_settings' in attrs_names:
            if node.attrs['scan_settings'] != '':
                scan_settings = node.attrs['scan_settings']
        pixmaps = []
        for attr in attrs_names:
            if 'pixmap' in attr:
                pixmaps.append(node.attrs[attr])

        return attr_dict, settings, scan_settings, pixmaps

    def get_h5_data(self, node_path):
        """

        Parameters
        ----------
        node_path: str
            the path in the file

        Returns
        -------
        data: ndarray
        axes: dict of Axis
            all the axis referring to the data: signal axes and navigation axes
        nav_axes: list of int
            index of the navigation axes
        is_spread: bool
            if True data is not in a regular grid (linear, 2D or ND) but given as a table with coordinates and value

        """
        node = self.get_node(node_path)
        is_spread = False
        if 'ARRAY' in node.attrs['CLASS']:
            data = node.read()
            nav_axes = []
            axes = dict([])
            if isinstance(data, np.ndarray):
                data = np.squeeze(data)
                if 'Bkg' in node.parent_node.children_name() and node.name != 'Bkg':
                    bkg = np.squeeze(self.get_node(node.parent_node.path, 'Bkg').read())
                    try:
                        data = data - bkg
                    except:
                        logger.warning(f'Could not substract bkg from data node {node_path} as their shape are '
                                       f'incoherent {bkg.shape} and {data.shape}')
                if 'type' in node.attrs.attrs_name:
                    if 'data' in node.attrs['type'] or 'channel' in node.attrs['type'].lower():
                        parent_path = node.parent_node.path
                        children = node.parent_node.children_name()

                        if 'data_dimension' not in node.attrs.attrs_name:  # for backcompatibility
                            data_dim = node.attrs['data_type']
                        else:
                            data_dim = node.attrs['data_dimension']
                        if 'scan_subtype' in node.attrs.attrs_name:
                            if node.attrs['scan_subtype'].lower() == 'adaptive':
                                is_spread = True
                        tmp_axes = ['x_axis', 'y_axis']
                        for ind, ax in enumerate(tmp_axes):
                            if capitalize(ax) in children:
                                axis_node = self.get_node(parent_path + '/{:s}'.format(capitalize(ax)))
                                axes[ax] = Axis(data=axis_node.read(), index=len(data.shape)-ind-1)
                                if 'units' in axis_node.attrs.attrs_name:
                                    axes[ax].units = axis_node.attrs['units']
                                if 'label' in axis_node.attrs.attrs_name:
                                    axes[ax].label = axis_node.attrs['label']
                            # else:
                            #     axes[ax] = Axis()

                        if data_dim == 'ND':  # check for navigation axis
                            tmp_nav_axes = ['y_axis', 'x_axis', ]
                            nav_axes = []
                            for ind_ax, ax in enumerate(tmp_nav_axes):
                                if 'Nav_{:s}'.format(ax) in children:
                                    nav_axes.append(ind_ax)
                                    axis_node = self.get_node(parent_path + '/Nav_{:s}'.format(ax))
                                    if is_spread:
                                        axes['nav_{:s}'.format(ax)] = Axis(data=axis_node.read())
                                    else:
                                        axes['nav_{:s}'.format(ax)] = Axis(data=np.unique(axis_node.read()))
                                        if axes['nav_{:s}'.format(ax)].data.shape[0] != data.shape[ind_ax]:
                                            # could happen in case of linear back to start type of scan
                                            tmp_ax = []
                                            for ix in axes['nav_{:s}'.format(ax)].data:
                                                tmp_ax.extend([ix, ix])
                                                axes['nav_{:s}'.format(ax)] = Axis(data=np.array(tmp_ax))

                                    if 'units' in axis_node.attrs.attrs_name:
                                        axes['nav_{:s}'.format(ax)].units = axis_node.attrs['units']
                                    if 'label' in axis_node.attrs.attrs_name:
                                        axes['nav_{:s}'.format(ax)].label = axis_node.attrs['label']

                        if 'scan_type' in node.attrs.attrs_name:
                            scan_type = node.attrs['scan_type'].lower()
                            # if scan_type == 'scan1d' or scan_type == 'scan2d':
                            scan_node, nav_children = find_scan_node(node)
                            nav_axes = []
                            if scan_type == 'tabular' or is_spread:
                                datas = []
                                labels = []
                                all_units = []
                                for axis_node in nav_children:
                                    npts = axis_node.attrs['shape'][0]
                                    datas.append(axis_node.read())
                                    labels.append(axis_node.attrs['label'])
                                    all_units.append(axis_node.attrs['units'])

                                nav_axes.append(0)
                                axes['nav_x_axis'] = NavAxis(
                                    data=np.linspace(0, npts - 1, npts),
                                    nav_index=nav_axes[-1], units='', label='Scan index', labels=labels,
                                    datas=datas, all_units=all_units)
                            else:
                                for axis_node in nav_children:
                                    nav_axes.append(axis_node.attrs['nav_index'])
                                    if is_spread:
                                        axes[f'nav_{nav_axes[-1]:02d}'] = Axis(data=axis_node.read(),
                                                                               index=nav_axes[-1])
                                    else:
                                        axes[f'nav_{nav_axes[-1]:02d}'] = Axis(data=np.unique(axis_node.read()),
                                                                               index=nav_axes[-1])
                                        if nav_axes[-1] < len(data.shape):
                                            if axes[f'nav_{nav_axes[-1]:02d}'].data.shape[0] != data.shape[nav_axes[-1]]:
                                                # could happen in case of linear back to start type of scan
                                                tmp_ax = []
                                                for ix in axes[f'nav_{nav_axes[-1]:02d}'].data:
                                                    tmp_ax.extend([ix, ix])
                                                    axes[f'nav_{nav_axes[-1]:02d}'] = Axis(data=np.array(tmp_ax),
                                                                                           index=nav_axes[-1])

                                    if 'units' in axis_node.attrs.attrs_name:
                                        axes[f'nav_{nav_axes[-1]:02d}'].units = axis_node.attrs[
                                            'units']
                                    if 'label' in axis_node.attrs.attrs_name:
                                        axes[f'nav_{nav_axes[-1]:02d}'].label = axis_node.attrs[
                                            'label']
                    elif 'axis' in node.attrs['type']:
                        axis_node = node
                        axes['y_axis'] = Axis(data=axis_node.read(), index=0)
                        if 'units' in axis_node.attrs.attrs_name:
                            axes['y_axis'].units = axis_node.attrs['units']
                        if 'label' in axis_node.attrs.attrs_name:
                            axes['y_axis'].label = axis_node.attrs['label']
                        # axes['x_axis'] = Axis(data=np.linspace(0, axis_node.attrs['shape'][0] - 1, axis_node.attrs['shape'][0]),
                        #                       units='pxls', label='', index=1)
                return data, axes, nav_axes, is_spread

            elif isinstance(data, list):
                return data, [], [], is_spread


class View(QObject):
    item_clicked_sig = Signal(object)
    item_double_clicked_sig = Signal(object)
    
    def __init__(self, widget: QtWidgets.QWidget, settings_tree, settings_attributes_tree):
        super().__init__()
        self.parent_widget = widget
        self.h5file_tree: TreeLayout = None

        self._viewer_widget: QtWidgets.QWidget = None
        self._text_list: QtWidgets.QListWidget = None
        self._pixmap_widget: QtWidgets.QWidget = None

        self.setup_ui(settings_tree, settings_attributes_tree)

    def setup_ui(self, settings_tree, settings_attributes_tree):
        layout = QtWidgets.QGridLayout()

        v_splitter = QtWidgets.QSplitter(Qt.Vertical)
        v_splitter2 = QtWidgets.QSplitter(Qt.Vertical)
        h_splitter = QtWidgets.QSplitter(Qt.Horizontal)

        widget = QtWidgets.QWidget()
        # self.ui.h5file_tree = TreeLayout(Form,col_counts=2,labels=["Node",'Pixmap'])
        self.h5file_tree = TreeLayout(widget, col_counts=1, labels=["Node"])
        self.h5file_tree.tree.setMinimumWidth(300)

        self.h5file_tree.item_clicked_sig.connect(self.item_clicked_sig.emit)
        self.h5file_tree.item_double_clicked_sig.connect(self.item_double_clicked_sig.emit)
        
        v_splitter.addWidget(widget)
        v_splitter.addWidget(settings_attributes_tree)

        h_splitter.addWidget(v_splitter)
        self._pixmap_widget = QtWidgets.QWidget()
        self._pixmap_widget.setMaximumHeight(100)
        v_splitter2.addWidget(self._pixmap_widget)

        v_splitter2.addWidget(settings_tree)
        self._text_list = QtWidgets.QListWidget()

        v_splitter2.addWidget(self._text_list)
        h_splitter.addWidget(v_splitter2)
        self._viewer_widget = QtWidgets.QWidget()
        h_splitter.addWidget(self._viewer_widget)
        layout.addWidget(h_splitter)
        self.parent_widget.setLayout(layout)

    def current_node_path(self):
        return self.h5file_tree.current_node_path()

    def add_actions(self, actions: List[QtWidgets.QAction]):
        for action in actions:
            self.h5file_tree.tree.addAction(action)
          
    @property  
    def viewer_widget(self):
        return self._viewer_widget

    @property
    def text_list(self):
        return self._text_list

    @property
    def pixmap_widget(self):
        return self._pixmap_widget

    def clear(self):
        self.h5file_tree.tree.clear()

    def add_base_item(self, base_tree_item):
        self.h5file_tree.tree.addTopLevelItem(base_tree_item)

    def add_widget_to_tree(self, pixmap_items):
        for item in pixmap_items:
            widget = QtWidgets.QWidget()

            vLayout = QtWidgets.QVBoxLayout()
            label1D = QtWidgets.QLabel()
            bytes = QByteArray(item['node'].attrs['pixmap1D'])
            im1 = QtGui.QImage.fromData(bytes)
            a = QtGui.QPixmap.fromImage(im1)
            label1D.setPixmap(a)

            label2D = QtWidgets.QLabel()
            bytes = QByteArray(item['node'].attrs['pixmap2D'])
            im2 = QtGui.QImage.fromData(bytes)
            b = QtGui.QPixmap.fromImage(im2)
            label2D.setPixmap(b)

            vLayout.addWidget(label1D)
            vLayout.addwidget(label2D)
            widget.setLayout(vLayout)
            self.h5file_tree.tree.setItemWidget(item['item'], 1, widget)


class H5Browser(QObject, ActionManager):
    """UI used to explore h5 files, plot and export subdatas

    Parameters
    ----------
    parent: QtWidgets container
        either a QWidget or a QMainWindow
    h5file: h5file instance
        exact type depends on the backend
    h5file_path: str or Path
        if specified load the corresponding file, otherwise open a select file dialog
    backend: str
        either 'tables, 'h5py' or 'h5pyd'

    See Also
    --------
    H5Backend, H5Backend
    """
    data_node_signal = Signal(str)  # the path of a node where data should be monitored, displayed...
    # whatever use from the caller
    status_signal = Signal(str)

    def __init__(self, parent: QtWidgets.QMainWindow, h5file=None, h5file_path=None, backend='tables'):
        QObject.__init__(self)
        # toolbar = QtWidgets.QToolBar()
        ActionManager.__init__(self)  # , toolbar=toolbar)

        if not isinstance(parent, QtWidgets.QMainWindow):
            raise Exception('no valid parent container, expected a QMainWindow')

        self.main_window = parent
        self.parent_widget = QtWidgets.QWidget()
        self.main_window.setCentralWidget(self.parent_widget)
        #self.main_window.addToolBar(self.toolbar)

        self.current_node_path = None

        self.settings_attributes = ParameterManager()
        self.settings = ParameterManager()

        # construct the UI interface
        self.view = View(self.parent_widget, settings_tree=self.settings.settings_tree,
                         settings_attributes_tree=self.settings_attributes.settings_tree)
        self.view.item_clicked_sig.connect(self.show_h5_attributes)
        self.view.item_double_clicked_sig.connect(self.show_h5_data)
        self.hyper_viewer = ViewerND(self.view.viewer_widget)

        self.setup_actions()
        self.setup_menu()
        self.connect_things()

        # construct the h5 interface and load the file (or open a select file message)
        self.h5utils = H5BrowserUtil(backend=backend)
        if h5file is None:
            if h5file_path is None:
                h5file_path = select_file(save=False, ext=['h5', 'hdf5'])
            if h5file_path != '':
                self.h5utils.open_file(h5file_path, 'r+')
            else:
                return
        else:
            self.h5utils.h5file = h5file
            
        self.data_loader = data_saving.DataLoader(self.h5utils)

        self.check_version()
        self.populate_tree()
        self.view.h5file_tree.expand_all()

    def connect_things(self):
        self.connect_action('export', self.export_data)
        self.connect_action('comment', self.add_comments)
        self.connect_action('load', self.load_file)
        self.connect_action('save', self.save_file)
        self.connect_action('quit', self.quit_fun)
        self.connect_action('about', self.show_about)
        self.connect_action('help', self.show_help)
        self.connect_action('log', self.show_log)

        self.connect_action('plot_node', lambda: self.get_node_and_plot(False))
        self.connect_action('plot_nodes', lambda: self.get_node_and_plot(False, True))
        self.connect_action('plot_node_with_bkg', lambda: self.get_node_and_plot(True))

        self.status_signal.connect(self.add_log)

    def get_node_and_plot(self, with_bkg, plot_all=False):
        self.show_h5_data(item=None, with_bkg=with_bkg, plot_all=plot_all)

    def load_file(self):
        #todo
        pass

    def setup_menu(self):
        menubar = self.main_window.menuBar()
        file_menu = menubar.addMenu('File')
        self.affect_to('load', file_menu)
        self.affect_to('save', file_menu)
        file_menu.addSeparator()
        self.affect_to('quit', file_menu)

        help_menu = menubar.addMenu('?')
        self.affect_to('about', help_menu)
        self.affect_to('help', help_menu)
        self.affect_to('log', help_menu)

    def setup_actions(self):
        self.add_action('export', 'Export as', 'SaveAs', tip='Export node content (and children) as ',
                        toolbar=self.toolbar)
        self.add_action('comment', 'Add Comment', 'properties', tip='Add comments to the node',
                        toolbar=self.toolbar)
        self.add_action('plot_node', 'Plot Node', 'color', tip='Plot the current node',
                        toolbar=self.toolbar)
        self.add_action('plot_nodes', 'Plot Nodes', 'color', tip='Plot all nodes hanging from the same parent',
                        toolbar=self.toolbar)
        self.add_action('plot_node_with_bkg', 'Plot Node With Bkg', 'color', tip='Plot the current node with background'
                                                                                 ' substraction if possible',
                        toolbar=self.toolbar)

        self.view.add_actions([self.get_action('export'), self.get_action('comment'),
                               self.get_action('plot_node'), self.get_action('plot_nodes'),
                               self.get_action('plot_node_with_bkg')])

        self.add_action('load', 'Load File', 'Open', tip='Open a new file')
        self.add_action('save', 'Save File as', 'SaveAs', tip='Save as another file')
        self.add_action('quit', 'Quit the application', 'Exit', tip='Quit the application')
        self.add_action('about', 'About', tip='About')
        self.add_action('help', 'Help', 'Help', tip='Show documentation', shortcut=QtCore.Qt.Key_F1)
        self.add_action('log', 'Show Log', 'information2', tip='Open Log')

    def check_version(self):
        """Check version of PyMoDAQ to assert if file is compatible or not with the current version of the Browser"""
        if 'pymodaq_version' in self.h5utils.root().attrs.attrs_name:
            if version_mod.parse(self.h5utils.root().attrs['pymodaq_version']) < version_mod.parse('4.0.0a0'):
                msg_box = messagebox(severity='warning', title='Invalid version',
                                     text=f"Your file has been saved using PyMoDAQ "
                                          f"version {self.h5utils.root().attrs['pymodaq_version']} "
                                          f"while you're using version: {utils.get_version()}\n"
                                          f"Please create and use an adapted environment to use this"
                                          f" version (up to 3.x.y):\n"
                                          f"pip install pymodaq==3.x.y")
                self.quit_fun()

    def add_comments(self, status: bool, comment=''):
        """Add comments to a node

        Parameters
        ----------
        status: bool
        comment: str
            The comment to be added in a comment attribute to the current node path

        See Also
        --------
        current_node_path
        """
        try:
            self.current_node_path = self.get_tree_node_path()
            node = self.h5utils.get_node(self.current_node_path)
            if 'comments' in node.attrs.attrs_name:
                tmp = node.attrs['comments']
            else:
                tmp = ''
            if comment == '':
                text, res = QtWidgets.QInputDialog.getMultiLineText(None, 'Enter comments', 'Enter comments here:', tmp)
                if res and text != '':
                    comment = text
                node.attrs['comments'] = comment
            else:
                node.attrs['comments'] = tmp + comment

            self.h5utils.flush()

        except Exception as e:
            logger.exception(str(e))

    def get_tree_node_path(self):
        """Get the node path of the currently selected node in the UI"""
        return self.view.current_node_path()

    def export_data(self):
        """Opens a dialog to export data

        See Also
        --------
        H5BrowserUtil.export_data
        """
        try:
            file_filter = "Single node h5 file (*.h5);;Text files (*.txt);;Ascii file (*.ascii)"
            file = select_file(save=True, filter=file_filter)
            self.current_node_path = self.get_tree_node_path()
            if file != '':
                self.h5utils.export_data(self.current_node_path, str(file))

        except Exception as e:
            logger.exception(str(e))

    def save_file(self, filename=None):

        if filename is None:
            filename = select_file(save=True, ext='txt')
        if filename != '':
            self.h5utils.save_file(filename)

    def quit_fun(self):
        """
        """
        try:
            self.h5utils.close_file()
            if self.main_window is None:
                self.parent_widget.close()
            else:
                self.main_window.close()
        except Exception as e:
            logger.exception(str(e))

    def show_about(self):
        splash_path = os.path.join(os.path.split(os.path.split(__file__)[0])[0], 'splash.png')
        splash = QtGui.QPixmap(splash_path)
        self.splash_sc = QtWidgets.QSplashScreen(splash, QtCore.Qt.WindowStaysOnTopHint)
        self.splash_sc.setVisible(True)
        self.splash_sc.showMessage(f"PyMoDAQ version {utils.get_version()}\n"
                                   f"Modular Acquisition with Python\nWritten by Sébastien Weber",
                                   QtCore.Qt.AlignRight, QtCore.Qt.white)

    @staticmethod
    def show_log():
        webbrowser.open(logging.getLogger('pymodaq').handlers[0].baseFilename)

    @staticmethod
    def show_help():
        QtGui.QDesktopServices.openUrl(QtCore.QUrl("http://pymodaq.cnrs.fr"))

    @staticmethod
    def add_log(txt):
        logger.info(txt)

    def show_h5_attributes(self, item=None):
        try:
            self.current_node_path = self.get_tree_node_path()

            attr_dict, settings, scan_settings, pixmaps = self.h5utils.get_h5_attributes(self.current_node_path)

            for child in self.settings_attributes.settings.children():
                child.remove()
            params = []
            for attr in attr_dict:
                params.append({'title': attr, 'name': attr, 'type': 'str', 'value': attr_dict[attr], 'readonly': True})
            self.settings_attributes.settings.addChildren(params)

            if settings is not None:
                for child in self.settings.settings.children():
                    child.remove()
                QtWidgets.QApplication.processEvents()  # so that the tree associated with settings updates
                params = pymodaq.utils.parameter.ioxml.XML_string_to_parameter(settings)
                self.settings.settings.addChildren(params)

            if scan_settings is not None:
                params = pymodaq.utils.parameter.ioxml.XML_string_to_parameter(scan_settings)
                self.settings.settings.addChildren(params)

            if pixmaps == []:
                self.view.pixmap_widget.setVisible(False)
            else:
                self.view.pixmap_widget.setVisible(True)
                self.show_pixmaps(pixmaps)

        except Exception as e:
            logger.exception(str(e))

    def show_pixmaps(self, pixmaps=[]):
        if self.view.pixmap_widget.layout() is None:
            self.view.pixmap_widget.setLayout(QtWidgets.QHBoxLayout())
        while 1:
            child = self.view.pixmap_widget.layout().takeAt(0)
            if not child:
                break
            child.widget().deleteLater()
            QtWidgets.QApplication.processEvents()
        labs = []
        for pix in pixmaps:
            labs.append(pngbinary2Qlabel(pix))
            self.view.pixmap_widget.layout().addWidget(labs[-1])

    def show_h5_data(self, item, with_bkg=False, plot_all=False):
        """
        """
        try:
            if item is None:
                self.current_node_path = self.get_tree_node_path()
            self.show_h5_attributes()
            node = self.h5utils.get_node(self.current_node_path)
            self.data_node_signal.emit(self.current_node_path)

            if 'data_type' in node.attrs and node.attrs['data_type'] == 'strings':
                self.view.text_list.clear()
                for txt in node.read():
                    self.view.text_list.addItem(txt)
            else:
                data_with_axes = self.data_loader.load_data(node, with_bkg=with_bkg, plot_all=plot_all)
                self.hyper_viewer.show_data(data_with_axes, force_update=True)

        except Exception as e:
            logger.exception(str(e))

    def populate_tree(self):
        """
            | Init the ui-tree and store data into calling the h5_tree_to_Qtree convertor method

            See Also
            --------
            h5tree_to_QTree, update_status
        """
        try:
            if self.h5utils.h5file is not None:
                self.view.clear()
                base_node = self.h5utils.root()
                base_tree_item, pixmap_items = h5tree_to_QTree(base_node)
                self.view.add_base_item(base_tree_item)
                self.view.add_widget_to_tree(pixmap_items)

        except Exception as e:
            logger.exception(str(e))


def browse_data(fname=None, ret_all=False, message=None):
    """Browse data present in any h5 file using the H5Browser within a dialog window
    when the user has selected a given node, return its content

    Parameters
    ----------
    fname: str
    ret_all: bool
    message: str

    Returns
    -------
    data: the numpy array in the selected node
    if argument ret_all is True, returns also:
    fname: the file name
    node_path: hte path of the selected node within the H5 file tree

    """
    if fname is None:
        fname = str(select_file(start_path=config('data_saving', 'h5file', 'save_path'), save=False, ext='h5'))

    if type(fname) != str:
        try:
            fname = str(fname)
        except Exception:
            raise Exception('filename in browse data is not valid')
    if fname != '':
        (root, ext) = os.path.splitext(fname)
        if not ('h5' in ext or 'hdf5' in ext):
            warnings.warn('This is not a PyMODAQ h5 file, there could be issues', Warning)

        form = QtWidgets.QWidget()
        browser = H5Browser(form, h5file_path=fname)

        dialog = QtWidgets.QDialog()
        vlayout = QtWidgets.QVBoxLayout()

        vlayout.addWidget(form)
        dialog.setLayout(vlayout)
        buttonBox = QtWidgets.QDialogButtonBox(parent=dialog)

        buttonBox.addButton('OK', buttonBox.AcceptRole)
        buttonBox.accepted.connect(dialog.accept)
        buttonBox.addButton('Cancel', buttonBox.RejectRole)
        buttonBox.rejected.connect(dialog.reject)
        vlayout.addWidget(buttonBox)

        dialog.setWindowTitle('Select a data node in the tree')
        if message is None or not isinstance(message, str):
            dialog.setWindowTitle('Select a data node in the tree')
        else:
            dialog.setWindowTitle(message)
        res = dialog.exec()

        if res == dialog.Accepted:
            node_path = browser.current_node_path
            data = browser.h5utils.get_node(node_path).read()
        else:
            data = None
            node_path = None

        browser.h5utils.close_file()

        if ret_all:
            return data, fname, node_path
        else:
            return data
    return None, '', ''


