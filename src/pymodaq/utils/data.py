# -*- coding: utf-8 -*-
"""
Created the 28/10/2022

@author: Sebastien Weber
"""

import numbers
import numpy as np
from typing import List, Tuple, Union
from typing import Iterable as IterableType
from collections.abc import Iterable

import warnings
from time import time
import copy

from multipledispatch import dispatch
from pymodaq.utils.enums import BaseEnum, enum_checker
from pymodaq.utils.messenger import deprecation_msg
from pymodaq.utils.daq_utils import find_objects_in_list_from_attr_name_val
from pymodaq.utils.logger import set_logger, get_module_name
from pymodaq.utils.slicing import SpecialSlicersData
from pymodaq.utils import math_utils as mutils

logger = set_logger(get_module_name(__file__))


class DataShapeError(Exception):
    pass


class DataLengthError(Exception):
    pass


class DataDim(BaseEnum):
    """Enum for dimensionality representation of data"""
    Data0D = 0
    Data1D = 1
    Data2D = 2
    DataND = 3


class DataSource(BaseEnum):
    """Enum for source of data"""
    raw = 0
    calculated = 1


class DataDistribution(BaseEnum):
    """Enum for distribution of data"""
    uniform = 0
    spread = 1


class Axis:
    """Object holding info and data about physical axis of some data

    In case the axis's data is linear, store the info as a scale and offset else store the data

    Parameters
    ----------
    label: str
        The label of the axis, for instance 'time' for a temporal axis
    units: str
        The units of the data in the object, for instance 's' for seconds
    data: ndarray
        A 1D ndarray holding the data of the axis
    index: int
        an integer representing the index of the Data object this axis is related to
    scaling: float
        The scaling to apply to a linspace version in order to obtain the proper scaling
    offset: float
        The offset to apply to a linspace/scaled version in order to obtain the proper axis
    """

    def __init__(self, label: str = '', units: str = '', data: np.ndarray = None, index: int = 0, scaling=None,
                 offset=None):
        super().__init__()

        self.iaxis = SpecialSlicersData(self, False)

        self._size = None
        self._data = None
        self._index = None
        self._label = None
        self._units = None
        self._scaling = scaling
        self._offset = offset

        self.units = units
        self.label = label
        self.data = data
        self.index = index

        self.get_scale_offset_from_data(data)

    @property
    def label(self) -> str:
        """str: get/set the label of this axis"""
        return self._label

    @label.setter
    def label(self, lab: str):
        if not isinstance(lab, str):
            raise TypeError('label for the Axis class should be a string')
        self._label = lab

    @property
    def units(self) -> str:
        """str: get/set the units for this axis"""
        return self._units

    @units.setter
    def units(self, units: str):
        if not isinstance(units, str):
            raise TypeError('units for the Axis class should be a string')
        self._units = units

    @property
    def index(self) -> int:
        """int: get/set the index this axis corresponds to in a DataWithAxis object"""
        return self._index

    @index.setter
    def index(self, ind: int):
        self._check_index_valid(ind)
        self._index = ind

    @property
    def data(self):
        """np.ndarray: get/set the data of Axis"""
        return self._data

    @data.setter
    def data(self, data: np.ndarray):
        if data is not None:
            self._check_data_valid(data)
            self._size = data.size
        else:
            self._size = 0
        self._data = data

    def get_data(self):
        return self._data if self._data is not None else self.create_linear_data(self.size)

    def get_scale_offset_from_data(self, data: np.ndarray = None):
        """Get the scaling and offset from the axis's data

        If data is not None, extract the scaling and offset

        Parameters
        ----------
        data: ndarray
        """
        if data is None and self._data is not None:
            data = self._data

        if self.is_axis_linear(data):
            self._scaling = np.mean(np.diff(data))
            self._offset = data[0]
            self._data = None

    def is_axis_linear(self, data=None):
        if data is None:
            data = self._data
        if data is not None:
            return np.allclose(np.diff(data), np.mean(np.diff(data)))
        else:
            return False

    @property
    def scaling(self):
        return self._scaling

    @scaling.setter
    def scaling(self, _scaling: float):
        self._scaling = _scaling

    @property
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, _offset: float):
        self._offset = _offset

    @property
    def size(self) -> int:
        """int: get/set the size/length of the 1D ndarray"""
        return self._size

    @size.setter
    def size(self, _size: int):
        if self._data is None:
            self._size = _size

    @staticmethod
    def _check_index_valid(index: int):
        if not isinstance(index, int):
            raise TypeError('index for the Axis class should be a positive integer')
        elif index < 0:
            raise ValueError('index for the Axis class should be a positive integer')

    @staticmethod
    def _check_data_valid(data):
        if not isinstance(data, np.ndarray):
            raise TypeError(f'data for the Axis class should be a 1D numpy array')
        elif len(data.shape) != 1:
            raise ValueError(f'data for the Axis class should be a 1D numpy array')

    def create_linear_data(self, nsteps:int):
        """replace the axis data with a linear version using scaling and offset if specified"""
        self.data = self._offset + self._scaling * np.linspace(0, nsteps-1, nsteps)

    @staticmethod
    def create_simple_linear_data(nsteps: int):
        return np.linspace(0, nsteps-1, nsteps)

    def __len__(self):
        return self.size

    def _slicer(self, _slice, *ignored, **ignored_also):
        ax = copy.deepcopy(self)
        if isinstance(_slice, int):
            return None
        elif isinstance(_slice, slice):
            if ax._data is not None:
                ax.data = ax._data.__getitem__(_slice)
                return ax
            else:
                ax._offset = ax.offset + _slice.start * ax.scaling
                ax._size = _slice.stop - _slice.start
                return ax

    def __getitem__(self, item):
        if hasattr(self, item):
            # for when axis was a dict
            deprecation_msg('attributes from an Axis object should not be fetched using __getitem__')
            return getattr(self, item)

    def __repr__(self):
        return f'{self.__class__.__name__}: <label: {self.label}> - <units: {self.units}> - <index: {self.index}>'

    def __mul__(self, scale: numbers.Real):
        if isinstance(scale, numbers.Real):
            ax = copy.deepcopy(self)
            if self.data is not None:
                ax.data *= scale
            else:
                ax._offset *= scale
                ax._scaling *= scale
            return ax

    def __add__(self, offset: numbers.Real):
        if isinstance(offset, numbers.Real):
            ax = copy.deepcopy(self)
            if self.data is not None:
                ax.data += offset
            else:
                ax._offset += offset
            return ax

    def __eq__(self, other):
        eq = self.label == other.label
        eq = eq and (self.units == other.units)
        eq = eq and (self.index == other.index)
        if self.data is not None and other.data is not None:
            eq = eq and (np.allclose(self.data, other.data))
        else:
            eq = eq and self.offset == other.offset
            eq = eq and self.scaling == other.scaling

        return eq

    def mean(self):
        if self._data is not None:
            return np.mean(self._data)
        else:
            return self.offset + self.size / 2 * self.scaling

    def min(self):
        if self._data is not None:
            return np.min(self._data)
        else:
            return self.offset + (self.size * self.scaling if self.scaling < 0 else 0)

    def max(self):
        if self._data is not None:
            return np.max(self._data)
        else:
            return self.offset + (self.size * self.scaling if self.scaling > 0 else 0)

    def find_index(self, threshold: float):
        """find the index of hte threshold value within the axis"""
        if self._data is not None:
            return mutils.find_index(self._data, threshold)[0][0]
        else:
            return int((threshold - self.offset) / self.scaling)


class NavAxis(Axis):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        deprecation_msg('NavAxis should not be used anymore, please use Axis object with correct index.'
                        'The navigation index should be specified in the Data object')


class DataLowLevel:
    """Abstract object for all Data Object

    Parameters
    ----------
    name: str
        the identifier of the data
    """

    def __init__(self, name: str):
        self._timestamp = time()
        self._name = name

    @property
    def name(self):
        """str: the identifier of the data"""
        return self._name

    @property
    def timestamp(self):
        """The timestamp of when the object has been created"""
        return self._timestamp


class DataBase(DataLowLevel):
    """Base object to store homogeneous data and metadata generated by pymodaq's objects. To be inherited for real data

    Parameters
    ----------
    name: str
        the identifier of these data
    source: DataSource or str
        Enum specifying if data are raw or processed (for instance from roi)
    dim: DataDim or str
        The identifier of the data type
    distribution: DataDistribution or str
        The distribution type of the data: uniform if distributed on a regular grid or spread if on specific
        unordered points
    data: list of ndarray
        The data the object is storing
    labels: list of str
        The labels of the data nd-arrays
    origin: str
        An identifier of the element where the data originated, for instance the DAQ_Viewer's name. Used when appending
        DataToExport in DAQ_Scan to desintricate from wich origin data comes from when scanning multiple detectors.

    See Also
    --------
    DataWithAxes, DataFromPlugins, DataRaw
    """

    def __init__(self, name: str, source: DataSource = None, dim: DataDim = None,
                 distribution: DataDistribution = DataDistribution['uniform'], data: List[np.ndarray] = None,
                 labels: List[str] = [], origin: str = None, **kwargs):

        super().__init__(name=name)
        self._iter_index = 0
        self._shape = None
        self._size = None
        self._data = None
        self._length = None
        self._labels = None
        self._dim = dim
        self.origin = origin

        source = enum_checker(DataSource, source)
        self._source = source

        distribution = enum_checker(DataDistribution, distribution)
        self._distribution = distribution

        self.data = data  # dim consistency is actually checked within the setter method

        self._check_labels(labels)
        for key in kwargs:
            setattr(self, key, kwargs[key])

    def get_full_name(self) -> str:
        """Get the data ful name including the origin attribute into the returned value

        Returns
        -------
        str: the name of the ataWithAxes data constructed as : origin/name

        Examples
        --------
        d0 = DataBase(name='datafromdet0', origin='det0')
        """
        return f'{self.origin}/{self.name}'

    def __repr__(self):
        return f'{self.__class__.__name__} <{self.name}> <{self.dim}> <{self.source}> <{self.shape}>'

    def __len__(self):
        return self.length

    def __iter__(self):
        self._iter_index = 0
        return self

    def __next__(self):
        if self._iter_index < len(self):
            self._iter_index += 1
            return self.data[self._iter_index-1]
        else:
            raise StopIteration

    def __getitem__(self, item):
        if isinstance(item, int) and 0 <= item < len(self):
            return self.data[item]
        else:
            raise IndexError(f'The index should be a positive integer lower than the data length')

    def __setitem__(self, key, value):
        if isinstance(key, int) and 0 <= key < len(self) and isinstance(value, np.ndarray) and value.shape == self.shape:
            self.data[key] = value
        else:
            raise IndexError(f'The index should be a positive integer lower than the data length')

    def __add__(self, other: object):
        if isinstance(other, DataBase) and len(other) == len(self):
            new_data = copy.deepcopy(self)
            for ind_array in range(len(new_data)):
                if self[ind_array].shape != other[ind_array].shape:
                    raise ValueError('The shapes of arrays stored into the data are not consistent')
                new_data[ind_array] = self[ind_array] + other[ind_array]
            return new_data
        else:
            raise TypeError(f'Could not add a {other.__class__.__name__} or a {self.__class__.__name__} '
                            f'of a different length')

    def __sub__(self, other: object):
        if isinstance(other, DataBase) and len(other) == len(self):
            new_data = copy.deepcopy(self)
            for ind_array in range(len(new_data)):
                new_data[ind_array] = self[ind_array] - other[ind_array]
            return new_data
        else:
            raise TypeError(f'Could not substract a {other.__class__.__name__} or a {self.__class__.__name__} '
                            f'of a different length')

    def __mul__(self, other):
        if isinstance(other, numbers.Number):
            new_data = copy.deepcopy(self)
            for ind_array in range(len(new_data)):
                new_data[ind_array] = self[ind_array] * other
            return new_data
        else:
            raise TypeError(f'Could not multiply a {other.__class__.__name__} and a {self.__class__.__name__} '
                            f'of a different length')

    def __truediv__(self, other):
        if isinstance(other, numbers.Number):
            return self * (1 / other)
        else:
            raise TypeError(f'Could not divide a {other.__class__.__name__} and a {self.__class__.__name__} '
                            f'of a different length')

    def __eq__(self, other):
        if isinstance(other, DataBase):
            if not(self.name == other.name and len(self) == len(other)):
                return False
            eq = True
            for ind in range(len(self)):
                if self[ind].shape != other[ind].shape:
                    eq = False
                    break
                eq = eq and np.allclose(self[ind], other[ind])
            return eq
        else:
            raise TypeError()

    def average(self, other: 'DataBase', weight: int) -> 'DataBase':
        """ Compute the weighted average between self and other DataBase and attributes it to self

        Parameters
        ----------
        other_data: DataBase
        weight: int
            The weight the 'other' holds with respect to self

        """
        if isinstance(other, DataBase) and len(other) == len(self) and isinstance(weight, numbers.Number):
            new_data = copy.copy(self)
            return (other * (weight - 1) + new_data) / weight
        else:
            raise TypeError(f'Could not average a {other.__class__.__name__} or a {self.__class__.__name__} '
                            f'of a different length')

    @property
    def shape(self):
        """The shape of the nd-arrays"""
        return self._shape

    @property
    def size(self):
        """The size of the nd-arrays"""
        return self._size

    @property
    def dim(self):
        """DataDim: the enum representing the dimensionality of the stored data"""
        return self._dim

    def set_dim(self, dim: Union[DataDim, str]):
        """Addhoc modification of dim independantly of the real data shape, should be used with extra care"""
        self._dim = enum_checker(DataDim, dim)

    @property
    def source(self):
        """DataSource: the enum representing the source of the data"""
        return self._source

    @property
    def distribution(self):
        """DataDistribution: the enum representing the distribution of the stored data"""
        return self._distribution

    @property
    def length(self):
        """The length of data. This is the length of the list containing the nd-arrays"""
        return self._length

    @property
    def labels(self):
        return self._labels

    def _check_labels(self, labels):
        while len(labels) < self.length:
            labels.append(f'CH{len(labels):02d}')
        self._labels = labels

    def get_data_index(self, index: int = 0):
        """Get the data by its index in the list"""
        return self.data[index]

    @staticmethod
    def _check_data_type(data: List[np.ndarray]) -> List[np.ndarray]:
        """make sure data is a list of nd-arrays"""
        is_valid = True
        if data is None:
            is_valid = False
        if not isinstance(data, list):
            # try to transform the data to regular type
            if isinstance(data, np.ndarray):
                warnings.warn(UserWarning(f'Your data should be a list of numpy arrays not just a single numpy array'
                                          f', wrapping them with a list'))
                data = [data]
            elif isinstance(data, numbers.Number):
                warnings.warn(UserWarning(f'Your data should be a list of numpy arrays not a scalar, wrapping it with a'
                                          f'list of numpy array'))
                data = [np.array([data])]
            else:
                is_valid = False
        if isinstance(data, list):
            if len(data) == 0:
                is_valid = False
            if not isinstance(data[0], np.ndarray):
                is_valid = False
            elif len(data[0].shape) == 0:
                is_valid = False
        if not is_valid:
            raise TypeError(f'Data should be an non-empty list of non-empty numpy arrays')
        return data

    def check_shape_from_data(self, data: List[np.ndarray]):
        self._shape = data[0].shape

    def get_dim_from_data(self, data: List[np.ndarray]):
        """Get the dimensionality DataDim from data"""
        self.check_shape_from_data(data)
        self._size = data[0].size
        self._length = len(data)
        if len(self._shape) == 1 and self._size == 1:
            dim = DataDim['Data0D']
        elif len(self._shape) == 1 and self._size > 1:
            dim = DataDim['Data1D']
        elif len(self._shape) == 2:
            dim = DataDim['Data2D']
        else:
            dim = DataDim['DataND']
        return dim

    def _check_shape_dim_consistency(self, data: List[np.ndarray]):
        """Process the dim from data or make sure data and DataDim are coherent"""
        dim = self.get_dim_from_data(data)
        if self._dim is None:
            self._dim = dim
        else:
            self._dim = enum_checker(DataDim, self._dim)
            if self._dim != dim:
                # warnings.warn(
                #     UserWarning('The specified dimensionality is not coherent with the data shape, replacing it'))
                self._dim = dim

    def _check_same_shape(self, data: List[np.ndarray]):
        """Check that all nd-arrays have the same shape"""
        for dat in data:
            if dat.shape != self.shape:
                raise DataShapeError('The shape of the ndarrays in data is not the same')

    @property
    def data(self):
        """List[np.ndarray]: get/set (and check) the data the object is storing"""
        return self._data

    @data.setter
    def data(self, data: List[np.ndarray]):
        data = self._check_data_type(data)
        self._check_shape_dim_consistency(data)
        self._check_same_shape(data)
        self._data = data


class AxesManager:
    def __init__(self, data_shape: Tuple[int], axes: List[Axis], nav_indexes=None, sig_indexes=None, **kwargs):
        self._data_shape = data_shape[:]  # initial shape needed for self._check_axis
        self._axes = axes[:]
        self._nav_indexes = nav_indexes
        self._sig_indexes = sig_indexes if sig_indexes is not None else self.compute_sig_indexes()

        self._check_axis(self._axes)
        self._manage_named_axes(self._axes, **kwargs)

    def compute_sig_indexes(self):
        _shape = list(self._data_shape)
        indexes = list(np.arange(len(self._data_shape)))
        for index in self.nav_indexes:
            if index in indexes:
                indexes.pop(indexes.index(index))
        return tuple(indexes)

    def compute_shape_from_axes(self):
        if len(self.axes) != 0:
            shape = []
            for ind in range(len(self.axes)):
                shape.append(len(self.get_axis_from_index(ind, create=True)))
        else:
            shape = self._data_shape
        return tuple(shape)

    @property
    def axes(self):
        return self._axes

    @axes.setter
    def axes(self, axes: List[Axis]):
        self._axes = axes[:]
        self._check_axis(self._axes)

    def _has_get_axis_from_index(self, index: int):
        """Check if the axis referred by a given data dimensionality index is present

        Returns
        -------
        bool: True if the axis has been found else False
        Axis or None: return the axis instance if has the axis else None
        """
        if index > len(self._data_shape) or index < 0:
            raise IndexError('The specified index does not correspond to any data dimension')
        for axis in self.axes:
            if axis.index == index:
                return True, axis
        return False, None

    def _manage_named_axes(self, axes, x_axis=None, y_axis=None, nav_x_axis=None, nav_y_axis=None):
        """This method make sur old style Data is still compatible, especially when using x_axis or y_axis parameters"""
        modified = False
        if x_axis is not None:
            modified = True
            index = 0
            if len(self._data_shape) == 1 and not self._has_get_axis_from_index(0)[0]:
                # in case of Data1D the x_axis corresponds to the first data dim
                index = 0
            elif len(self._data_shape) == 2 and not self._has_get_axis_from_index(1)[0]:
                # in case of Data2D the x_axis corresponds to the second data dim (columns)
                index = 1
            axes.append(Axis(x_axis.label, x_axis.units, x_axis.data, index=index))

        if y_axis is not None:

            if len(self._data_shape) == 2 and not self._has_get_axis_from_index(0)[0]:
                modified = True
                # in case of Data2D the y_axis corresponds to the first data dim (lines)
                axes.append(Axis(y_axis.label, y_axis.units, y_axis.data, index=0))

        if nav_x_axis is not None:
            if len(self.nav_indexes) > 0:
                modified = True
                # in case of DataND the y_axis corresponds to the first data dim (lines)
                axes.append(Axis(nav_x_axis.label, nav_x_axis.units, nav_x_axis.data, index=self._nav_indexes[0]))

        if nav_y_axis is not None:
            if len(self.nav_indexes) > 1:
                modified = True
                # in case of Data2D the y_axis corresponds to the first data dim (lines)
                axes.append(Axis(nav_y_axis.label, nav_y_axis.units, nav_y_axis.data, index=self._nav_indexes[1]))

        if modified:
            self._check_axis(axes)

    @property
    def shape(self) -> Tuple[int]:
        self._data_shape = self.compute_shape_from_axes()
        return self._data_shape

    @property
    def sig_shape(self) -> tuple:
        return tuple([self.shape[ind] for ind in self.sig_indexes])

    @property
    def nav_shape(self) -> tuple:
        return tuple([self.shape[ind] for ind in self.nav_indexes])

    def append_axis(self, axis: Axis):
        self._axes.append(axis)
        self._check_axis([axis])

    @property
    def nav_indexes(self) -> IterableType[int]:
        return self._nav_indexes

    @nav_indexes.setter
    def nav_indexes(self, nav_indexes: IterableType[int]):
        if isinstance(nav_indexes, Iterable):
            nav_indexes = tuple(nav_indexes)
            valid = True
            for index in nav_indexes:
                if index not in self.get_axes_index():
                    logger.warning('Could not set the corresponding nav_index into the data object, not enough'
                                   ' Axis declared')
                    valid = False
                    break
            if valid:
                self._nav_indexes = nav_indexes
        else:
            logger.warning('Could not set the corresponding sig_indexes into the data object, should be an iterable')
        self.sig_indexes = self.compute_sig_indexes()

    @property
    def sig_indexes(self) -> IterableType[int]:
        return self._sig_indexes

    @sig_indexes.setter
    def sig_indexes(self, sig_indexes: IterableType[int]):
        if isinstance(sig_indexes, Iterable):
            sig_indexes = tuple(sig_indexes)
            valid = True
            for index in sig_indexes:
                if index in self._nav_indexes:
                    logger.warning('Could not set the corresponding sig_index into the axis manager object, '
                                   'the axis is already affected to the navigation axis')
                    valid = False
                    break
                if index not in self.get_axes_index():
                    logger.warning('Could not set the corresponding nav_index into the data object, not enough'
                                   ' Axis declared')
                    valid = False
                    break
            if valid:
                self._sig_indexes = sig_indexes
        else:
            logger.warning('Could not set the corresponding sig_indexes into the data object, should be an iterable')

    @property
    def nav_axes(self) -> List[int]:
        deprecation_msg('nav_axes parameter should not be used anymore, use nav_indexes')
        return self._nav_indexes

    @nav_axes.setter
    def nav_axes(self, nav_indexes: List[int]):
        deprecation_msg('nav_axes parameter should not be used anymore, use nav_indexes')
        self.nav_indexes = nav_indexes

    def is_axis_signal(self, axis: Axis) -> bool:
        """Check if an axis is considered signal or navigation"""
        return axis.index in self._nav_indexes

    def is_axis_navigation(self, axis: Axis) -> bool:
        """Check if an axis  is considered signal or navigation"""
        return axis.index not in self._nav_indexes

    def get_shape_from_index(self, index: int) -> int:
        """Get the data shape at the given index"""
        if index > len(self._data_shape) or index < 0:
            raise IndexError('The specified index does not correspond to any data dimension')
        return self._data_shape[index]

    def _check_axis(self, axes: List[Axis]):
        """Check all axis to make sure of their type and make sure their data are properly referring to the data index

        See Also
        --------
        :py:meth:`Axis.create_linear_data`
        """
        for ind, axis in enumerate(axes):
            if not isinstance(axis, Axis):
                raise TypeError(f'An axis of {self.__class__.__name__} should be an Axis object')
            if self.get_shape_from_index(axis.index) != axis.size:
                warnings.warn(UserWarning('The size of the axis is not coherent with the shape of the data. '
                                          'Replacing it with a linspaced version: np.array([0, 1, 2, ...])'))
                axis.size = self.get_shape_from_index(axis.index)
                axis.scaling = 1
                axis.offset = 0
                axes[ind] = axis
        self._axes = axes

    def get_axes_index(self) -> List[int]:
        """Get the index list from the axis objects"""
        return [axis.index for axis in self._axes]

    def get_axis_from_index(self, index: int, create: bool = False) -> Axis:
        """Get the axis referred by a given data dimensionality index

        If the axis is absent, create a linear one to fit the data shape if parameter create is True

        Parameters
        ----------
        index: int
            The index referring to the data ndarray shape
        create: bool
            If True and the axis referred by index has not been found in axes, create one

        Returns
        -------
        Axis or None: return the axis instance if Data has the axis (or it has been created) else None

        See Also
        --------
        :py:meth:`Axis.create_linear_data`
        """
        has_axis, axis = self._has_get_axis_from_index(index)
        if not has_axis:
            if create:
                warnings.warn(
                    UserWarning(f'The axis requested with index {index} is not present, creating a linear one...'))
                axis = Axis(data=np.zeros((1,)), index=index)
                axis.create_linear_data(self.get_shape_from_index(index))
            else:
                warnings.warn(
                    UserWarning(f'The axis requested with index {index} is not present, returning None'))
        return axis

    def get_nav_axes(self):
        return [copy.copy(self.get_axis_from_index(index, create=True)) for index in self.nav_indexes]

    def get_signal_axes(self):
        if self.sig_indexes is None:
            self._sig_indexes = tuple([axis.index for axis in self.axes if axis.index not in self.nav_indexes])
        return [copy.copy(self.get_axis_from_index(index, create=True)) for index in self.sig_indexes]

    def is_axis_signal(self, axis: Axis) -> bool:
        """Check if an axis is considered signal or navigation"""
        return axis.index in self._nav_indexes

    def is_axis_navigation(self, axis: Axis) -> bool:
        """Check if an axis  is considered signal or navigation"""
        return axis.index not in self._nav_indexes

    def __repr__(self):
        return self._get_dimension_str()

    def _get_dimension_str(self):
        string = "("
        for nav_index in self.nav_indexes:
            string += str(self._data_shape[nav_index]) + ", "
        string = string.rstrip(", ")
        string += "|"
        for sig_index in self.sig_indexes:
            string += str(self._data_shape[sig_index]) + ", "
        string = string.rstrip(", ")
        string += ")"
        return string


class AxesManagerSpread:
        def __init__(self, data_shape: Tuple[int], axes: List[Axis], nav_indexes=None, sig_indexes=None, **kwargs):
            self._data_shape = data_shape[:]  # initial shape needed for self._check_axis
            self._axes = axes[:]
            self._nav_indexes = nav_indexes
            self._sig_indexes = sig_indexes if sig_indexes is not None else self.compute_sig_indexes()

            self._check_axis(axes)
            self._manage_named_axes(axes, **kwargs)

        def compute_sig_indexes(self):
            _shape = list(self._data_shape)
            indexes = list(np.arange(len(self._data_shape)))
            for index in self.nav_indexes:
                if index in indexes:
                    indexes.pop(indexes.index(index))
            return tuple(indexes)

        def compute_shape_from_axes(self):
            shape = []
            for ind in range(len(self.axes)):
                shape.append(len(self.get_axis_from_index(ind, create=True)))
            return tuple(shape)

        @property
        def axes(self):
            return self._axes

        def _has_get_axis_from_index(self, index: int):
            """Check if the axis referred by a given data dimensionality index is present

            Returns
            -------
            bool: True if the axis has been found else False
            Axis or None: return the axis instance if has the axis else None
            """
            if index > len(self._data_shape) or index < 0:
                raise IndexError('The specified index does not correspond to any data dimension')
            for axis in self.axes:
                if axis.index == index:
                    return True, axis
            return False, None

        def _manage_named_axes(self, axes, x_axis=None, y_axis=None, nav_x_axis=None, nav_y_axis=None):
            """This method make sur old style Data is still compatible, especially when using x_axis or y_axis parameters"""
            modified = False
            if x_axis is not None:
                modified = True
                index = 0
                if len(self._data_shape) == 1 and not self._has_get_axis_from_index(0)[0]:
                    # in case of Data1D the x_axis corresponds to the first data dim
                    index = 0
                elif len(self._data_shape) == 2 and not self._has_get_axis_from_index(1)[0]:
                    # in case of Data2D the x_axis corresponds to the second data dim (columns)
                    index = 1
                axes.append(Axis(x_axis.label, x_axis.units, x_axis.data, index=index))

            if y_axis is not None:

                if len(self._data_shape) == 2 and not self._has_get_axis_from_index(0)[0]:
                    modified = True
                    # in case of Data2D the y_axis corresponds to the first data dim (lines)
                    axes.append(Axis(y_axis.label, y_axis.units, y_axis.data, index=0))

            if nav_x_axis is not None:
                if len(self.nav_indexes) > 0:
                    modified = True
                    # in case of DataND the y_axis corresponds to the first data dim (lines)
                    axes.append(Axis(nav_x_axis.label, nav_x_axis.units, nav_x_axis.data, index=self._nav_indexes[0]))

            if nav_y_axis is not None:
                if len(self.nav_indexes) > 1:
                    modified = True
                    # in case of Data2D the y_axis corresponds to the first data dim (lines)
                    axes.append(Axis(nav_y_axis.label, nav_y_axis.units, nav_y_axis.data, index=self._nav_indexes[1]))

            if modified:
                self._check_axis(axes)

        @property
        def shape(self) -> Tuple[int]:
            self._data_shape = self.compute_shape_from_axes()
            return self._data_shape

        @property
        def sig_shape(self) -> tuple:
            return tuple([self.shape[ind] for ind in self.sig_indexes])

        @property
        def nav_shape(self) -> tuple:
            return tuple([self.shape[ind] for ind in self.nav_indexes])

        def append_axis(self, axis: Axis):
            self._axes.append(axis)
            self._check_axis([axis])

        @property
        def nav_indexes(self) -> IterableType[int]:
            return self._nav_indexes

        @nav_indexes.setter
        def nav_indexes(self, nav_indexes: IterableType[int]):
            if isinstance(nav_indexes, Iterable):
                nav_indexes = tuple(nav_indexes)
                valid = True
                for index in nav_indexes:
                    if index not in self.get_axes_index():
                        logger.warning('Could not set the corresponding nav_index into the data object, not enough'
                                       ' Axis declared')
                        valid = False
                        break
                if valid:
                    self._nav_indexes = nav_indexes
            else:
                logger.warning(
                    'Could not set the corresponding sig_indexes into the data object, should be an iterable')
            self.sig_indexes = self.compute_sig_indexes()

        @property
        def sig_indexes(self) -> IterableType[int]:
            return self._sig_indexes

        @sig_indexes.setter
        def sig_indexes(self, sig_indexes: IterableType[int]):
            if isinstance(sig_indexes, Iterable):
                sig_indexes = tuple(sig_indexes)
                valid = True
                for index in sig_indexes:
                    if index in self._nav_indexes:
                        logger.warning('Could not set the corresponding sig_index into the axis manager object, '
                                       'the axis is already affected to the navigation axis')
                        valid = False
                        break
                    if index not in self.get_axes_index():
                        logger.warning('Could not set the corresponding nav_index into the data object, not enough'
                                       ' Axis declared')
                        valid = False
                        break
                if valid:
                    self._sig_indexes = sig_indexes
            else:
                logger.warning(
                    'Could not set the corresponding sig_indexes into the data object, should be an iterable')

        @property
        def nav_axes(self) -> List[int]:
            deprecation_msg('nav_axes parameter should not be used anymore, use nav_indexes')
            return self._nav_indexes

        @nav_axes.setter
        def nav_axes(self, nav_indexes: List[int]):
            deprecation_msg('nav_axes parameter should not be used anymore, use nav_indexes')
            self.nav_indexes = nav_indexes

        def is_axis_signal(self, axis: Axis) -> bool:
            """Check if an axis is considered signal or navigation"""
            return axis.index in self._nav_indexes

        def is_axis_navigation(self, axis: Axis) -> bool:
            """Check if an axis  is considered signal or navigation"""
            return axis.index not in self._nav_indexes

        def get_shape_from_index(self, index: int) -> int:
            """Get the data shape at the given index"""
            if index > len(self._data_shape) or index < 0:
                raise IndexError('The specified index does not correspond to any data dimension')
            return self._data_shape[index]

        def _check_axis(self, axes: List[Axis]):
            """Check all axis to make sure of their type and make sure their data are properly referring to the data index

            See Also
            --------
            :py:meth:`Axis.create_linear_data`
            """
            for ind, axis in enumerate(axes):
                if not isinstance(axis, Axis):
                    raise TypeError(f'An axis of {self.__class__.name} should be an Axis object')
                if self.get_shape_from_index(axis.index) != axis.size:
                    warnings.warn(UserWarning('The size of the axis is not coherent with the shape of the data. '
                                              'Replacing it with a linspaced version: np.array([0, 1, 2, ...])'))
                    axes[ind].create_linear_data(self.get_shape_from_index(axis.index))
            self._axes = axes

        def get_axes_index(self) -> List[int]:
            """Get the index list from the axis objects"""
            return [axis.index for axis in self._axes]

        def get_axis_from_index(self, index: int, create: bool = False) -> Axis:
            """Get the axis referred by a given data dimensionality index

            If the axis is absent, create a linear one to fit the data shape if parameter create is True

            Parameters
            ----------
            index: int
                The index referring to the data ndarray shape
            create: bool
                If True and the axis referred by index has not been found in axes, create one

            Returns
            -------
            Axis or None: return the axis instance if Data has the axis (or it has been created) else None

            See Also
            --------
            :py:meth:`Axis.create_linear_data`
            """
            has_axis, axis = self._has_get_axis_from_index(index)
            if not has_axis:
                if create:
                    warnings.warn(
                        UserWarning(f'The axis requested with index {index} is not present, creating a linear one...'))
                    axis = Axis(data=np.zeros((1,)), index=index)
                    axis.create_linear_data(self.get_shape_from_index(index))
                else:
                    warnings.warn(
                        UserWarning(f'The axis requested with index {index} is not present, returning None'))
            return axis

        def get_nav_axes(self):
            return [copy.copy(self.get_axis_from_index(index, create=True)) for index in self.nav_indexes]

        def get_signal_axes(self):
            if self.sig_indexes is None:
                self._sig_indexes = tuple([axis.index for axis in self.axes if axis.index not in self.nav_indexes])
            return [copy.copy(self.get_axis_from_index(index, create=True)) for index in self.sig_indexes]

        def is_axis_signal(self, axis: Axis) -> bool:
            """Check if an axis is considered signal or navigation"""
            return axis.index in self._nav_indexes

        def is_axis_navigation(self, axis: Axis) -> bool:
            """Check if an axis  is considered signal or navigation"""
            return axis.index not in self._nav_indexes

        def __repr__(self):
            return self._get_dimension_str()

        def _get_dimension_str(self):
            string = "("
            for nav_index in self.nav_indexes:
                string += str(self._data_shape[nav_index]) + ", "
            string = string.rstrip(", ")
            string += "|"
            for sig_index in self.sig_indexes:
                string += str(self._data_shape[sig_index]) + ", "
            string = string.rstrip(", ")
            string += ")"
            return string


class DataWithAxes(DataBase):
    """Data object with Axis objects corresponding to underlying data nd-arrays

    Parameters
    ----------
    axes: list of Axis
        the list of Axis object for proper plotting, calibration ...
    nav_indexes: tuple of int
        highlight which Axis in axes is Signal or Navigation axis depending on the content:
        For instance, nav_indexes = (2,), means that the axis with index 2 in a at least 3D ndarray data is the first
        navigation axis
        For instance, nav_indexes = (3,2), means that the axis with index 3 in a at least 4D ndarray data is the first
        navigation axis while the axis with index 2 is the second navigation Axis. Axes with index 0 and 1 are signal
        axes of 2D ndarray data
    """

    def __init__(self, *args, axes: List[Axis] = [], nav_indexes: Tuple[int] = (), **kwargs):

        if 'nav_axes' in kwargs:
            deprecation_msg('nav_axes parameter should not be used anymore, use nav_indexes')
            nav_indexes = kwargs.pop('nav_axes')

        x_axis = kwargs.pop('x_axis') if 'x_axis' in kwargs else None
        y_axis = kwargs.pop('y_axis') if 'y_axis' in kwargs else None

        nav_x_axis = kwargs.pop('nav_x_axis') if 'nav_x_axis' in kwargs else None
        nav_y_axis = kwargs.pop('nav_y_axis') if 'nav_y_axis' in kwargs else None

        super().__init__(*args, **kwargs)

        self._axes = axes

        other_kwargs = dict(x_axis=x_axis, y_axis=y_axis, nav_x_axis=nav_x_axis, nav_y_axis=nav_y_axis)

        self.axes_manager = AxesManager(data_shape=self.shape, axes=axes, nav_indexes=nav_indexes, **other_kwargs)

        self.inav = SpecialSlicersData(self, True)
        self.isig = SpecialSlicersData(self, False)

        self.get_dim_from_data_axes()

    def __repr__(self):
        return f'<{self.__class__.__name__}, {self.name}, {self._am}>'

    def transpose(self):
        if self.dim == 'Data2D':
            self.data[:] = [data.T for data in self.data]
            for axis in self.axes:
                axis.index = 0 if axis.index == 1 else 1

    def get_dim_from_data_axes(self):
        """Get the dimensionality DataDim from data taking into account nav indexes
        """
        if len(self.nav_indexes) > 0:
            self._dim = DataDim['DataND']

    @property
    def axes(self):
        """convenience property to fetch attribute from axis_manager"""
        return self._am.axes

    @axes.setter
    def axes(self, axes: List[Axis]):
        """convenience property to set attribute from axis_manager"""
        self._am.axes = axes

    @property
    def sig_indexes(self):
        """convenience property to fetch attribute from axis_manager"""
        return self._am.sig_indexes

    @property
    def nav_indexes(self):
        """convenience property to fetch attribute from axis_manager"""
        return self._am.nav_indexes

    @nav_indexes.setter
    def nav_indexes(self, indexes: List[int]):
        """convenience property to fetch attribute from axis_manager"""
        self._am.nav_indexes = indexes

    def get_nav_axes(self) -> List['Axis']:
        return self._am.get_nav_axes()

    def get_nav_axes_with_data(self) -> List['Axis']:
        """Get the data's navigation axes making sure there is data in the data field"""
        axes = self.get_nav_axes()
        for axis in axes:
            if axis.data is None:
                axis.create_linear_data(self.shape[axis.index])
        return axes

    def get_axis_from_index(self, index, create=False):
        return self._am.get_axis_from_index(index, create)

    def _compute_slices(self, slices, is_navigation=True):
        """Compute the total slice to apply to the data

        Filling in Ellipsis when no slicing should be done
        """
        if is_navigation:
            indexes = self._am.nav_indexes
        else:
            indexes = self._am.sig_indexes
        total_slices = []
        slices = list(slices)
        for ind in range(len(self.shape)):
            if ind in indexes:
                total_slices.append(slices.pop(0))
            elif len(total_slices) == 0 or total_slices[-1] != Ellipsis:
                total_slices.append(Ellipsis)
        total_slices = tuple(total_slices)
        return total_slices

    def _slicer(self, slices, is_navigation=True):
        """Apply a given slice to the data either navigation or signal dimension

        Parameters
        ----------
        slices: tuple of slice or int
            the slices to apply to the data
        is_navigation: bool
            if True apply the slices to the navigation dimension else to the signal ones

        Returns
        -------
        DataWithAxes
            Object of the same type as the initial data, derived from DataWithAxes. But with lower data size due to the
             slicing and with eventually less axes.
        """

        if isinstance(slices, numbers.Number) or isinstance(slices, slice):
            slices = [slices]
        total_slices = self._compute_slices(slices, is_navigation)
        new_arrays_data = [np.atleast_1d(np.squeeze(dat[total_slices])) for dat in self.data]
        axes_to_append = self._am.get_signal_axes() if is_navigation else self._am.get_nav_axes()
        indexes_to_get = self._am.nav_indexes if is_navigation else self._am.sig_indexes

        lower_indexes = dict(zip([ind for ind in range(len(self.axes))], [0 for _ in range(len(self.axes))]))
        axes = []
        nav_indexes = [] if is_navigation else self._am.nav_indexes
        for ind_slice, _slice in enumerate(slices):
            ax = self._am.get_axis_from_index(indexes_to_get[ind_slice])
            ax = ax.iaxis[_slice]
            if ax is not None:  # means the slice keep part of the axis
                if is_navigation:
                    nav_indexes.append(self._am.nav_indexes[ind_slice])
                axes.append(ax)
            else:
                for axis in axes_to_append:  # means we removed one of the nav axes (and data dim),
                    # hence axis index above current nav_index should be lowered by 1
                    if axis.index > indexes_to_get[ind_slice]:
                        lower_indexes[axis.index] += 1
        for axis in axes_to_append:
            axis.index -= lower_indexes[axis.index]

        axes.extend(axes_to_append)
        data = DataWithAxes(self.name, data=new_arrays_data, nav_indexes=nav_indexes, axes=axes, source='calculated')
        return data

    def deepcopy_with_new_data(self, data: List[np.ndarray] = None, remove_axes_index: List[int] = None):
        """deepcopy without copying the initial data (saving memory)

        The new data, may have some axes stripped as specified in remove_axes_index
        """
        try:
            old_data = self.data
            self._data = None
            new_data = self.deepcopy()
            new_data._data = data

            if not isinstance(remove_axes_index, Iterable):
                remove_axes_index = [remove_axes_index]

            if remove_axes_index is not None:
                for index in remove_axes_index:
                    new_data._am.axes.pop(new_data._am.axes.index(new_data._am.get_axis_from_index(index)))
                    if index in new_data._am.nav_indexes:
                        nav_indexes = list(new_data._am.nav_indexes)
                        nav_indexes.pop(nav_indexes.index(index))
                        new_data._am.nav_indexes = tuple(nav_indexes)
                    if index in new_data._am.sig_indexes:
                        sig_indexes = list(new_data._am.sig_indexes)
                        sig_indexes.pop(sig_indexes.index(index))
                        new_data._am.sig_indexes = tuple(sig_indexes)
            new_data._shape = data[0].shape
            new_data._dim = self.get_dim_from_data(data)
            return new_data
        except Exception as e:
            pass
        finally:
            self._data = old_data

    def deepcopy(self):
        return copy.deepcopy(self)

    @property
    def _am(self) -> AxesManager:
        return self.axes_manager

    def get_data_dimension(self) -> str:
        return str(self._am)


class DataRaw(DataWithAxes):
    """Specialized DataWithAxes set with source as 'raw'. To be used for raw data"""
    def __init__(self, *args,  **kwargs):
        if 'source' in kwargs:
            kwargs.pop('source')
        super().__init__(*args, source=DataSource['raw'], **kwargs)


class DataFromPlugins(DataRaw):
    """Specialized DataWithAxes set with source as 'raw'. To be used for raw data generated by plugins"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class DataCalculated(DataWithAxes):
    """Specialized DataWithAxes set with source as 'calculated'. To be used for processed/calculated data"""
    def __init__(self, *args, axes=[],  **kwargs):
        if 'source' in kwargs:
            kwargs.pop('source')
        super().__init__(*args, source=DataSource['calculated'], axes=axes, **kwargs)


class DataFromRoi(DataCalculated):
    """Specialized DataWithAxes set with source as 'calculated'.To be used for processed data from region of interest"""
    def __init__(self, *args, axes=[], **kwargs):
        super().__init__(*args, axes=axes, **kwargs)


class DataToExport(DataLowLevel):
    """Object to store all raw and calculated DataWithAxes data for later exporting, saving, sending signal...

    Includes methods to retrieve data from dim, source...
    Stored data have a unique identifier their name. If some data is appended with an existing name, it will replace
    the existing data. So if you want to append data that has the same name

    Parameters
    ----------
    name: str
        The identifier of the exporting object
    data: list of DataWithAxes
        All the raw and calculated data to be exported

    Attributes
    ----------
    name
    timestamp
    data
    """

    def __init__(self, name: str, data: List[DataWithAxes] = [], **kwargs):
        """

        Parameters
        ----------
        name
        data
        """
        super().__init__(name)
        if not isinstance(data, list):
            raise TypeError('Data stored in a DataToExport object should be as a list of objects'
                            ' inherited from DataWithAxis')
        self._data = []

        self.data = data
        for key in kwargs:
            setattr(self, key, kwargs[key])

    def affect_name_to_origin_if_none(self):
        """Affect self.name to all DataWithAxes children's attribute origin if this origin is not defined"""
        for dat in self.data:
            if dat.origin is None:
                dat.origin = self.name

    def __sub__(self, other: object):
        if isinstance(other, DataToExport) and len(other) == len(self):
            new_data = copy.deepcopy(self)
            for ind_dfp in range(len(self)):
                new_data[ind_dfp] = self[ind_dfp] - other[ind_dfp]
            return new_data
        else:
            raise TypeError(f'Could not substract a {other.__class__.__name__} or a {self.__class__.__name__} '
                            f'of a different length')

    def __add__(self, other: object):
        if isinstance(other, DataToExport) and len(other) == len(self):
            new_data = copy.deepcopy(self)
            for ind_dfp in range(len(self)):
                new_data[ind_dfp] = self[ind_dfp] + other[ind_dfp]
            return new_data
        else:
            raise TypeError(f'Could not add a {other.__class__.__name__} or a {self.__class__.__name__} '
                            f'of a different length')

    def __mul__(self, other: object):
        if isinstance(other, numbers.Number):
            new_data = copy.deepcopy(self)
            for ind_dfp in range(len(self)):
                new_data[ind_dfp] = self[ind_dfp] * other
            return new_data
        else:
            raise TypeError(f'Could not multiply a {other.__class__.__name__} with a {self.__class__.__name__} '
                            f'of a different length')

    def __truediv__(self, other: object):
        if isinstance(other, numbers.Number):
            return self * (1 / other)
        else:
            raise TypeError(f'Could not divide a {other.__class__.__name__} with a {self.__class__.__name__} '
                            f'of a different length')

    def average(self, other: 'DataToExport', weight: int) -> 'DataToExport':
        """ Compute the weighted average between self and other DataToExport and attributes it to self

        Parameters
        ----------
        other: DataToExport
        weight: int
            The weight the 'other_data' holds with respect to self

        """
        if isinstance(other, DataToExport) and len(other) == len(self):
            new_data = copy.copy(self)
            for ind_dfp in range(len(self)):
                new_data[ind_dfp] = self[ind_dfp].average(other[ind_dfp], weight)
            return new_data
        else:
            raise TypeError(f'Could not average a {other.__class__.__name__} with a {self.__class__.__name__} '
                            f'of a different length')

    def __repr__(self):
        return f'{self.__class__.__name__}: {self.name} <len:{len(self)}>'

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        self._iter_index = 0
        return self

    def __next__(self) -> DataWithAxes:
        if self._iter_index < len(self):
            self._iter_index += 1
            return self.data[self._iter_index-1]
        else:
            raise StopIteration

    def __getitem__(self, item) -> DataWithAxes:
        if isinstance(item, int) and 0 <= item < len(self):
            return self.data[item]
        else:
            raise IndexError(f'The index should be a positive integer lower than the data length')

    def __setitem__(self, key, value: DataWithAxes):
        if isinstance(key, int) and 0 <= key < len(self) and isinstance(value, DataWithAxes):
            self.data[key] = value
        else:
            raise IndexError(f'The index should be a positive integer lower than the data length')

    def get_names(self, dim: DataDim = None):
        """Get the names of the stored DataWithAxes,  eventually filtered by dim

        Parameters
        ----------
        dim: DataDim or str

        Returns
        -------
        list of str: the names of the (filtered) DataWithAxes data
        """
        if dim is None:
            return [data.name for data in self.data]
        else:
            return [data.name for data in self.get_data_from_dim(dim).data]

    def get_full_names(self, dim: DataDim = None):
        """Get the ful names including the origin attribute into the returned value,  eventually filtered by dim

        Parameters
        ----------
        dim: DataDim or str

        Returns
        -------
        list of str: the names of the (filtered) DataWithAxes data constructed as : origin/name

        Examples
        --------
        d0 = DataWithAxes(name='datafromdet0', origin='det0')
        """
        if dim is None:
            return [data.get_full_name() for data in self.data]
        else:
            return [data.get_full_name() for data in self.get_data_from_dim(dim).data]

    def get_data_from_full_names(self, full_names: List[str], deepcopy=False) -> 'DataToExport':
        if deepcopy:
            data = [self.get_data_from_name_origin(full_name.split('/')[1],
                                                   full_name.split('/')[0]).deepcopy() for full_name in full_names]
        else:
            data = [self.get_data_from_name_origin(full_name.split('/')[1],
                                                   full_name.split('/')[0]) for full_name in full_names]
        return DataToExport(name=self.name, data=data)

    def get_dim_presents(self) -> List[str]:
        dims = []
        for dim in DataDim.names():
            if len(self.get_data_from_dim(dim)) != 0:
                dims.append(dim)

        return dims

    def get_data_from_dim(self, dim: DataDim, deepcopy=False) -> 'DataToExport':
        """Get the data matching the given DataDim

        Returns
        -------
        DataToExport: filtered with data matching the dimensionality
        """
        dim = enum_checker(DataDim, dim)
        selection = find_objects_in_list_from_attr_name_val(self.data, 'dim', dim, return_first=False)
        selection.sort(key=lambda elt: elt[0].name)
        if deepcopy:
            data = [sel[0].deepcopy() for sel in selection]
        else:
            data = [sel[0] for sel in selection]
        return DataToExport(name=self.name, data=data)

    def get_data_from_dims(self, dims: List[DataDim], deepcopy=False) -> 'DataToExport':
        """Get the data matching the given DataDim

        Returns
        -------
        DataToExport: filtered with data matching the dimensionality
        """
        data = DataToExport(name=self.name)
        for dim in dims:
            data.append(self.get_data_from_dim(dim, deepcopy=deepcopy))
        return data

    def get_data_from_name(self, name: str) -> List[DataWithAxes]:
        """Get the data matching the given name"""
        data, _ = find_objects_in_list_from_attr_name_val(self.data, 'name', name, return_first=True)
        return data

    def get_data_from_name_origin(self, name: str, origin: str = None) -> DataWithAxes:
        """Get the data matching the given name and the given origin"""
        if origin is None:
            data, _ = find_objects_in_list_from_attr_name_val(self.data, 'name', name, return_first=True)
        else:
            selection = find_objects_in_list_from_attr_name_val(self.data, 'name', name, return_first=False)
            selection = [sel[0] for sel in selection]
            data, _ = find_objects_in_list_from_attr_name_val(selection, 'origin', origin)
        return data

    def index(self, data: DataWithAxes):
        return self.data.index(data)

    def index_from_name_origin(self, name: str, origin: str = None) -> List[DataWithAxes]:
        """Get the index of a given DataWithAxes within the list of data"""
        """Get the data matching the given name and the given origin"""
        if origin is None:
            _, index = find_objects_in_list_from_attr_name_val(self.data, 'name', name, return_first=True)
        else:
            selection = find_objects_in_list_from_attr_name_val(self.data, 'name', name, return_first=False)
            data_selection = [sel[0] for sel in selection]
            index_selection = [sel[1] for sel in selection]
            _, index = find_objects_in_list_from_attr_name_val(data_selection, 'origin', origin)
            index = index_selection[index]
        return index

    def pop(self, index: int) -> DataWithAxes:
        """return and remove the DataWithAxes referred by its index

        Parameters
        ----------
        index: int
            index as returned by self.index_from_name_origin

        See Also
        --------
        index_from_name_origin
        """
        return self.data.pop(index)

    @property
    def data(self) -> List[DataWithAxes]:
        """List[DataWithAxes]: get the data contained in the object"""
        return self._data

    @data.setter
    def data(self, new_data: List[DataWithAxes]):
        for dat in new_data:
            self._check_data_type(dat)
        self._data[:] = [dat for dat in new_data]  # shallow copyto make sure that if the original list
        # is changed, the change will not be applied in here

        self.affect_name_to_origin_if_none()

    @staticmethod
    def _check_data_type(data: DataWithAxes):
        """Make sure data is a DataWithAxes object or inherited"""
        if not isinstance(data, DataWithAxes):
            raise TypeError('Data stored in a DataToExport object should be objects inherited from DataWithAxis')

    @dispatch(list)
    def append(self, data: List[DataWithAxes]):
        for dat in data:
            self.append(dat)

    @dispatch(DataWithAxes)
    def append(self, data: DataWithAxes):
        """Append/replace DataWithAxes object to the data attribute

        Make sure only one DataWithAxes object with a given name is in the list except if they don't have the same
        origin identifier
        """
        data = copy.deepcopy(data)
        self._check_data_type(data)
        obj = self.get_data_from_name_origin(data.name, data.origin)
        if obj is not None:
            self._data.pop(self.data.index(obj))
        self._data.append(data)

    @dispatch(object)
    def append(self, data: 'DataToExport'):
        if isinstance(data, DataToExport):
            for dat in data:
                self.append(dat)


class DataScan(DataToExport):
    """Specialized DataToExport.To be used for data to be saved """
    def __init__(self, name: str, data: List[DataWithAxes] = [], **kwargs):
        super().__init__(name, data, **kwargs)


if __name__ == '__main__':
    from pymodaq.utils import math_utils as mutils

    d1 = DataFromRoi(name=f'Hlineout_', data=[np.zeros((24,))],
                     x_axis=Axis(data=np.zeros((24,)), units='myunits', label='mylabel1'))
    d2 = DataFromRoi(name=f'Hlineout_', data=[np.zeros((12,))],
                     x_axis=Axis(data=np.zeros((12,)),
                                 units='myunits2',
                                 label='mylabel2'))

    Nsig = 200
    Nnav = 10
    x = np.linspace(-Nsig/2, Nsig/2-1, Nsig)

    dat = np.zeros((Nnav, Nsig))
    for ind in range(Nnav):
        dat[ind] = mutils.gauss1D(x,  50 * (ind -Nnav / 2), 25 / np.sqrt(2))

    data = DataRaw('mydata', data=[dat], nav_indexes=(0,),
                   axes=[Axis('nav', data=np.linspace(0, Nnav-1, Nnav), index=0),
                         Axis('sig', data=x, index=1)])

    data2 = copy.copy(data)

    data3 = data._deepcopy_with_new_data([np.sum(dat, 1)], remove_axes_index=(1,))

    print('done')

