# -*- coding: utf-8 -*-
"""
Created on Thu Feb 29 16:12:05 2024

@author: weber
"""
import pytest

import numpy as np
import tempfile
from pathlib import Path

from pymodaq.utils import math_utils as mutils
from pymodaq.utils import data as datamod
from pymodaq.utils.h5modules.saving import H5SaverLowLevel
from pymodaq.utils.h5modules.data_saving import DataSaverLoader, DataEnlargeableSaver


@pytest.fixture(scope="module")
def get_3D_array():
    # import tempfile
    # from pathlib import Path
    # import zipfile
    # from urllib.request import urlretrieve
    # import nibabel
    #
    # # Create a temporary directory
    # with tempfile.TemporaryDirectory() as directory_name:
    #     directory = Path(directory_name)
    #     # Define URL
    #     url = 'http://www.fil.ion.ucl.ac.uk/spm/download/data/attention/attention.zip'
    #
    #     # Retrieve the data
    #     fn, info = urlretrieve(url, directory.joinpath('attention.zip'))
    #
    #     # Extract the contents into the temporary directory we created earlier
    #     zipfile.ZipFile(fn).extractall(path=directory)
    #
    #     # Read the image
    #     struct = nibabel.load(directory.joinpath('attention/structural/nsM00587_0002.hdr'))
    #
    #     # Get a plain NumPy array, without all the metadata
    #     array_3D = struct.get_fdata()
    p = Path(__file__).parent.parent.parent
    array_3D = np.load(p.joinpath('data/my_brain.npy'))

    return array_3D


@pytest.fixture()
def get_h5saver(tmp_path):
    h5saver = H5SaverLowLevel()
    addhoc_file_path = tmp_path.joinpath('h5file.h5')
    h5saver.init_file(file_name=addhoc_file_path)

    yield h5saver
    h5saver.close_file()

class Test1DPlot:
    def test_plot_0D_1D_uniform(self, qtbot):
        #%%
        NX = 100
        x_axis = datamod.Axis('xaxis', 'xunits', data=np.linspace(-20, 50, NX), index=0)
        data_array_1D = mutils.gauss1D(x_axis.get_data(), 10, 5)

        dwa_1D = datamod.DataRaw('data1DUniform', data=[data_array_1D, -data_array_1D],
                                 axes=[x_axis])
        print(dwa_1D)
        assert dwa_1D.distribution.name == 'uniform'
        assert dwa_1D.dim.name == 'Data1D'
        assert dwa_1D.shape == (NX,)

        dwa_1D.plot('qt')

        with tempfile.TemporaryDirectory() as d:
            with DataSaverLoader(Path(d).joinpath('mydatafile.h5')) as saver_loader:
                saver_loader.add_data('/RawData', dwa_1D)

                dwa_back = saver_loader.load_data('/RawData/Data00', load_all=True)

                assert dwa_back == dwa_1D

    def test_plot_1D_0D_uniform(self, qtbot):
        #%%
        NX = 100
        x_axis = datamod.Axis('xaxis', 'xunits', data=np.linspace(-20, 50, NX), index=0)
        data_array_1D = mutils.gauss1D(x_axis.get_data(), 10, 5)

        dwa_1D = datamod.DataRaw('data1DUniform', data=[data_array_1D, -data_array_1D],
                                 axes=[x_axis],
                                 nav_indexes=(0,))
        print(dwa_1D)
        assert dwa_1D.distribution.name == 'uniform'
        assert dwa_1D.dim.name == 'DataND'
        assert dwa_1D.shape == (NX,)

        dwa_1D.plot('qt')

        with tempfile.TemporaryDirectory() as d:
            with DataSaverLoader(Path(d).joinpath('mydatafile.h5')) as saver_loader:
                saver_loader.add_data('/RawData', dwa_1D)
                dwa_back = saver_loader.load_data('/RawData/Data00', load_all=True)
                assert dwa_back == dwa_1D


    def test_plot_1D_0D_spread(self, qtbot):

        NX = 100
        axis_spread_array = np.linspace(-20, 50, NX)
        np.random.shuffle(axis_spread_array)
        data_array_1D_spread = mutils.gauss1D(axis_spread_array, 20, 5)

        axis_spread = datamod.Axis('axis spread', 'units', data=axis_spread_array)

        data1D_spread = datamod.DataRaw('data1DSpread', data=[data_array_1D_spread],
                                        distribution='spread',
                                        nav_indexes=(0,),
                                        axes=[axis_spread])
        print(data1D_spread)
        assert data1D_spread.distribution.name == 'spread'
        assert data1D_spread.dim.name == 'DataND'
        assert data1D_spread.shape == (NX,)
        data1D_spread.plot('qt')

        with tempfile.TemporaryDirectory() as d:
            with DataSaverLoader(Path(d).joinpath('mydatafile.h5')) as saver_loader:
                saver_loader.add_data('/RawData', data1D_spread)

                dwa_back = saver_loader.load_data('/RawData/Data00', load_all=True)

                assert dwa_back == data1D_spread

    def test_plot_0D_1D_spread(self, qtbot, get_h5saver):
        # when loading data from an enlarged array with a nav axis of size 0, there is an extra dimension
        #in the array of len 1: shape = (1, N) simulated here by using expand_dims
        h5saver = get_h5saver
        data_saver = DataEnlargeableSaver(h5saver)
        NX = 100
        axis_array = np.linspace(-20, 50, NX)
        data_array_1D = mutils.gauss1D(axis_array, 20, 5)
        axis_sig = datamod.Axis('axis spread', 'units', data=axis_array, index=0)
        data_to_append = datamod.DataRaw('data1D', data=[data_array_1D],
                                         axes=[axis_sig])

        axis_value = 12.

        data_saver.add_data('/RawData', data_to_append, axis_values=[axis_value])

        dwa_back = data_saver.load_data('/RawData/EnlData00', load_all=True)
        assert dwa_back.inav[0] == data_to_append
        dwa_back.plot('qt')

        data_saver.add_data('/RawData', data_to_append, axis_values=[axis_value+1])
        dwa_back = data_saver.load_data('/RawData/EnlData00', load_all=True)
        assert dwa_back.inav[1] == data_to_append
        dwa_back.plot('qt')

        data_saver.add_data('/RawData', data_to_append, axis_values=[axis_value + 2])
        dwa_back = data_saver.load_data('/RawData/EnlData00', load_all=True)
        assert dwa_back.inav[2] == data_to_append
        dwa_back.plot('qt')


class Test2DPlot:
    def test_plot_0D_2D_uniform(self, qtbot):
        NX = 100
        NY = 50

        x_axis = datamod.Axis('xaxis', 'xunits', data=np.linspace(-20, 50, NX), index=1)
        y_axis = datamod.Axis('yaxis', 'yunits', data=np.linspace(20, 40, NY), index=0)
        data_array_2D = mutils.gauss2D(x_axis.get_data(), 0, 5, y_axis.get_data(), 30, 5)

        data2D = datamod.DataRaw('data2DUniform', data=[data_array_2D],
                                 axes=[x_axis, y_axis])
        print(data2D)
        assert data2D.distribution == 'uniform'
        assert data2D.dim == 'Data2D'
        data2D.plot('qt')

    @pytest.mark.parametrize('nav_index', (0, 1))
    def test_plot_1D_1D_uniform(self, qtbot, nav_index):
        NX = 100
        NY = 50

        x_axis = datamod.Axis('xaxis', 'xunits', data=np.linspace(-20, 50, NX), index=1)
        y_axis = datamod.Axis('yaxis', 'yunits', data=np.linspace(20, 40, NY), index=0)
        data_array_2D = mutils.gauss2D(x_axis.get_data(), 0, 5, y_axis.get_data(), 30, 5)

        data2D = datamod.DataRaw('data2DUniform', data=[data_array_2D],
                                 axes=[x_axis, y_axis],
                                 nav_indexes=(nav_index,))
        print(data2D)
        assert data2D.distribution == 'uniform'
        assert data2D.dim == 'DataND'
        data2D.plot('qt')

    def test_plot_2D_0D_uniform(self, qtbot):
        NX = 100
        NY = 50

        x_axis = datamod.Axis('xaxis', 'xunits', data=np.linspace(-20, 50, NX), index=1)
        y_axis = datamod.Axis('yaxis', 'yunits', data=np.linspace(20, 40, NY), index=0)
        data_array_2D = mutils.gauss2D(x_axis.get_data(), 0, 5, y_axis.get_data(), 30, 5)

        data2D = datamod.DataRaw('data2DUniform', data=[data_array_2D],
                                 axes=[x_axis, y_axis],
                                 nav_indexes=(0, 1))
        print(data2D)
        assert data2D.distribution == 'uniform'
        assert data2D.dim == 'DataND'
        data2D.plot('qt')

    def test_plot_2D_0D_spread(self, qtbot):
        N = 100
        x_axis_array = np.random.randint(-20, 50, size=N)
        y_axis_array = np.random.randint(20, 40, size=N)
        x_axis = datamod.Axis('xaxis', 'xunits', data=x_axis_array, index=0, spread_order=0)
        y_axis = datamod.Axis('yaxis', 'yunits', data=y_axis_array, index=0, spread_order=1)

        data_list = []
        for ind in range(N):
            data_list.append(mutils.gauss2D(x_axis.get_data()[ind], 0, 5,
                                            y_axis.get_data()[ind], 30, 5))
        data_array = datamod.squeeze(np.array(data_list))
        data_array.shape

        data2D_spread = datamod.DataRaw('data2DSpread', data=[data_array],
                                        axes=[x_axis, y_axis],
                                        distribution='spread',
                                        nav_indexes=(0,))
        print(data2D_spread)
        assert data2D_spread.distribution == 'spread'
        assert data2D_spread.dim == 'DataND'

        data2D_spread.plot('qt')


    def test_plot_1D_1D_spread(self, qtbot):
        N = 10
        axis_array = np.linspace(0, 2*np.pi, N)
        axis = datamod.Axis('axis', 'units', data=axis_array, index=0, spread_order=0)

        NX = 100
        x_axis = datamod.Axis('xaxis', 'xunits', data=np.linspace(-20, 50, NX), index=1)
        data_array_1D = mutils.gauss1D(x_axis.get_data(), 10, 5)

        data_list = []
        for ind in range(N):
            data_list.append(data_array_1D * np.sin(axis_array[ind]))

        data_array = datamod.squeeze(np.array(data_list))
        assert data_array.shape == (N, NX)

        data2D_spread = datamod.DataRaw('data2DSpread', data=[data_array],
                                        axes=[axis, x_axis],
                                        distribution='spread',
                                        nav_indexes=(0,))
        print(data2D_spread)
        assert data2D_spread.distribution == 'spread'
        assert data2D_spread.dim == 'DataND'

        data2D_spread.plot('qt')


class Test3DPlot:
    @pytest.mark.parametrize('nav_index', ((0,), (1,), (2,), (0, 1), (0, 2), (1, 2)))
    def test_plot_0D_3D_uniform(self, qtbot, get_3D_array, nav_index):

        data3D = datamod.DataRaw('data3DUniform', data=[get_3D_array],
                                 nav_indexes=nav_index,
                                 )
        data3D.create_missing_axes()

        print(data3D)
        assert data3D.distribution == 'uniform'
        assert data3D.dim == 'DataND'
        data3D.plot('qt')


if __name__ == '__main__':
    from qtpy import QtWidgets
    import sys
    import tempfile
    from pathlib import Path

    # with tempfile.TemporaryDirectory() as d:
    #     h5saver = H5SaverLowLevel()
    #     h5saver.init_file(file_name=Path(d).joinpath('myh5.h5'))

    app = QtWidgets.QApplication(sys.argv)
    test = Test3DPlot()
    test.test_plot_0D_3D_uniform(None, np.load(r'C:\Users\weber\Labo\Programmes Python\PyMoDAQ_Git\pymodaq\tests\utils\data/my_brain.npy'))

        # h5saver.close_file()

    sys.exit(app.exec_())