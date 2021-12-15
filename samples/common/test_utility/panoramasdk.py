import sys
import os
import time
import json
import logging
from logging.handlers import RotatingFileHandler

import IPython
import matplotlib.pyplot as plt
import cv2
import dlr

# configure DLR
dlr.counter.phone_home.PhoneHome.disable_feature()

# configure logging
logging.basicConfig(filename="SimulatorLog.log")
log_p = logging.getLogger('panoramasdk')
log_p.setLevel(logging.DEBUG)
handler = RotatingFileHandler("SimulatorLog.log", maxBytes=100000000, backupCount=2)
formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)
log_p.addHandler(handler)

# configure matplotlib
plt.rcParams["figure.figsize"] = (20, 20)

# -------
# Globals

_c = None
_graph = None

# -------
# Custom exceptions

class TestUtilityBaseError(Exception):
    pass

class TestUtilityEndOfVideo(TestUtilityBaseError):
    pass

# -------

def _configure( config ):
    
    global _c
    
    _c = config


class media(object):

    """
    This class mimics the Media object in Panoroma SDK .

    ...

    Attributes
    ----------
    inputpath : str
        input path is a string path to a video file

    gen : video_reader instance

    Methods
    -------
    video_reader(key)
        CV2 based Generator for Video

    image : Property
        Gets the next frame using the generator

    image : Property Setter
        If we want to set the value of stream.image

    add_label:
        Add text to frame

    add_rect:
        add rectangles to frame

    time_stamp:
        returns the current timestamp

    stream_uri:
        returns a hardcoded value for now

    """

    def __init__(self, array):
        self.image = array
        self.w, self.h, self.c = array.shape

    @property
    def image(self):
        return self.__image

    @image.setter
    def image(self, array):
        self.__image = array

    def add_label(self, text, x1, y1):

        if x1 > 1 or y1 > 1:
            raise ValueError('Value should be between 0 and 1')

        # font
        font = cv2.FONT_HERSHEY_SIMPLEX
        # org
        org = (int(x1 * self.h), int(y1 * self.w))

        # fontScale
        fontScale = 1

        # White in BGR
        color = (255, 255, 255)

        # Line thickness of 2 px
        thickness = 2

        # Using cv2.putText() method
        self.__image = cv2.putText(self.__image, text, org, font,
                                   fontScale, color, thickness, cv2.LINE_AA)

    def add_rect(self, x1, y1, x2, y2):

        if x1 > 1 or y1 > 1 or x2 > 1 or y2 > 1:
            raise ValueError('Value should be between 0 and 1')

        # Red in BGR
        color = (0, 0, 255)

        # Line thickness of 2 px
        thickness = 2

        start_point = (int(x1 * self.h), int(y1 * self.w))
        end_point = (int(x2 * self.h), int(y2 * self.w))

        self.__image = cv2.rectangle(
            self.__image,
            start_point,
            end_point,
            color,
            thickness)

    @property
    def time_stamp(self):
        micro = 1000000
        t = int( time.time() * micro )
        return ( t // micro, t % micro )

    @property
    def stream_uri(self):
        """Hardcoded Value for Now"""

        return 'cam1'


class AccessWithDot:

    """
    This class is implemented so we can mimic accessing dictionary keys with a .

    ...

    Attributes
    ----------
    response : dictionary
        Input is a dictionary object


    Methods
    -------
    __getattr__(key)
        First, try to return from _response
    """

    def __init__(self, response):
        self.__dict__['_response'] = response
        self.op_name = list(response.keys())[0] # "op_name" is not used anywhere

    def __getattr__(self, key):
        # First, try to return from _response
        try:
            return self.__dict__['_response'][key]
        except KeyError as e:
            log_p.info('Key {} Not Found. Please Check {} package.json'.format(
                    e, _c.code_package_name))
        # If that fails, return default behavior so we don't break Python
        try:
            return self.__dict__[key]
        except KeyError:
            raise AttributeError
            log_p.info('Attribute Error')


# FIXME : data structure has to be reconsidered to represent graph data correctly
class getgraphdata:

    """
    Helper Class to Collect List of Nodes and Edges from the Graph.json

    Parameters
    ----------
    None
    """

    def __init__(self):
        pass

    def getlistofnodes(self):
        # read graph.json

        # get nodes into a dict
        graph_nodes = _graph['nodeGraph']['nodes']

        # create node_dict
        node_dict = {}
        for d in graph_nodes:
            for key in d.keys():
                # FIXME : this code is assuming "name" is always the first key
                if key == 'name':
                    node_name = d[key]
                    node_dict[node_name] = [node_name]  # {}
                elif key != 'name':
                    node_dict[node_name].append(d[key])
            
            node_dict[node_name].append(d)
            

            # get edge name from edge dict from Node name
            edge_dict = self.getlistofedges()

            try:
                node_name_edge = edge_dict[node_name]
            except BaseException: # FIXME : should be more specific exception type
                node_name_edge = node_name

            # use the above name in the node dict
            node_dict[node_name_edge] = port(node_dict[node_name])

        return node_dict

    def getlistofedges(self):

        # read graph.json

        # get edges into a dict
        graph_edges = _graph['nodeGraph']['edges']

        # create edge_dict
        edge_dict = {}
        for d in graph_edges:
            edge_dict[d['producer'].split(
                '.')[0]] = d['consumer'].split('.')[1]

        return edge_dict

    def getoutputsfrompackagejson(self):
        # read package.json from main package
        path = './{}/packages/'.format(_c.app_name) + \
            _c.account_id + '-' + _c.code_package_name + '-1.0/' + 'package.json'

        # Read Graph
        with open(path) as f:
            package_json = json.load(f)

        # FIXME : if interfaces is empty, this line raises IndexError, which is difficult to understand how to solve the issue
        output_name = package_json["nodePackage"]["interfaces"][0]["outputs"][0]["name"]

        return output_name


###### Video array CLASS #####

class Video_Array(object):

    """
    This class is implemented so we can use the opencv VideoCapture Method

    ...

    Attributes
    ----------
    inputpath :
        Input is a path to a video


    Methods
    -------
    get_frame
        returns a frame at a time until it exceeds _c.video_range
    """

    def __init__(self, inputpath):

        self.input_path = inputpath

        assert _c.video_range.start >= 0, "Config.video_range.start has to be >= 0."
        assert _c.video_range.stop > 0, "Config.video_range.stpp has to be positive integer."
        assert _c.video_range.step > 0, "Config.video_range.step has to be positive integer."

    def get_frame(self):
        
        if not os.path.exists(self.input_path):
            raise FileNotFoundError( self.input_path )
        
        cap = cv2.VideoCapture(self.input_path)
        frame_num = 0

        # Skip first frames based on video_range.start
        for i in range(0,_c.video_range.start):
            _, frame = cap.read()
            frame_num += 1
            
            if frame is None:
                return

        while (frame_num <= _c.video_range.stop):
            
            _, frame = cap.read()
            frame_num += 1

            if frame is None:
                return
            
            # Reading frame one by one to reduce memory space
            yield frame

            # Skip frames based on video_range.step
            for i in range(1,_c.video_range.step):
                _, frame = cap.read()
                frame_num += 1


class port():

    """
    Port Class Mock on the Device Panorama SDK

    Parameters
    ----------
    call_node : Dict

    Methods
    -------
    get : Gets the next frame from the video provided as a generator object
    """

    def __init__(self, call_node):
        
        self.call_node = call_node
        self.frame_output = []

        # classifying call_node
        self.call_node_type = 'call_node_name'
        self.call_node_location = None
        for val in self.call_node[:-1]:
            if not isinstance(
                    val, bool) and isinstance(
                    val, str) and len(
                    val.split('.')) > 1:
                self.call_node_type = 'call_node_location'
                self.call_node_location = val
                break
            elif isinstance(val, bool) or type(val) in [int, float]:
                continue

        # RTSP Stream Video Frames Creation
        if self.call_node_type == 'call_node_location' and self.call_node_location.split(
                '.')[-2].split('::')[1] == _c.camera_node_name:

            if _c.camera_node_name != 'abstract_rtsp_media_source':

                # 'reading in the video / rtsp stream'
                path = './{}/packages/{}-{}-1.0/package.json'.format( _c.app_name, _c.account_id, self.call_node_location.split('.')[0].split('::')[1] )
                with open(path) as f:
                    package = json.load(f)
                rtsp_url = package['nodePackage']['interfaces'][0]['inputs'][-1]['default']

                # this may be temp or perm dont know yet
                if rtsp_url.split('.')[-1] in ['avi', 'mp4']:
                    rtsp_url = './{}/assets/'.format(_c.app_name) + rtsp_url

            elif _c.camera_node_name == 'abstract_rtsp_media_source':
                log_p.info('{}'.format('Using Abstract Data Source'))

            self.video_obj = Video_Array(_c.videoname).get_frame()

    def get(self):
        if self.call_node_type == 'call_node_name':
            return self.call_node[-1]['value']
        elif self.call_node_location.split('.')[-2].split('::')[1] == _c.camera_node_name:
            # video frame invoker
            try:
                return [media(next(self.video_obj))]
            except StopIteration:
                raise TestUtilityEndOfVideo("Reached end of video")
        else:
            # Shouldn't come here. Raise exception with helpful error message.
            assert False


#### OUTPUT CLASS #######

class OutputClass(object):
    """
    Output Class is a helper function for Port Class

    Parameters
    ----------
    initial : Frame Object to be displayed

    Methods
    -------
    None

    """
    
    screenshot_n_frame = 0

    def __init__(self, initial=None):
        
        self._list = initial
        
        if _c.screenshot_dir:
            for i_img, img in enumerate(self._list):
                filename = f"{_c.screenshot_dir}/screenshot_%d_%04d.png" % ( i_img, OutputClass.screenshot_n_frame )
                cv2.imwrite( filename, img.image )
            
            OutputClass.screenshot_n_frame += 1
        
        if _c.render_output_image_with_pyplot:
            for img in self._list:
                IPython.display.clear_output(wait=True)
                plt.imshow( cv2.cvtColor(img.image,cv2.COLOR_BGR2RGB) )
                plt.show()


################# CLASS DEFS DONE ##########################

class node(object):
    """
    This class is implemented to mimic Panoroma Node Class.

    ...

    Attributes
    ----------

    Methods
    -------
    """
    
    # Add properties and methods to the instance
    @staticmethod
    def _initialize(instance):
    
        global _graph

        # Read graph.json
        with open("./{}/graphs/{}/graph.json".format( _c.app_name, _c.app_name )) as f:
            _graph = json.load(f)

        node_dict = getgraphdata().getlistofnodes()

        instance.inputs = AccessWithDot(node_dict)
        
        output_name = getgraphdata().getoutputsfrompackagejson()
        instance.outputs = AccessWithDot(
            {output_name: AccessWithDot({'put': OutputClass})})
    
    # Create node instance
    # This method is automatically called even if it is not called explicitly
    def __new__(cls, *args, **kwargs):

        instance = super(node,cls).__new__(cls, *args, **kwargs)

        node._initialize( instance )

        node._dlr_models = {}

        return instance

    # Instantiate DLRModel when it is used for the first time, 
    # and check if the model node/interface are correctly defined in JSON files
    def _load_dlr_model( self, name ):

        # Check if the supplied name is valid or not
        # Step 1: Get the interface for the model_package_name provided
        model_pkg = './{}/packages/'.format(_c.app_name) + '/{}-{}'.format(_c.account_id, _c.model_package_name) + '-1.0/' + 'package.json'
        with open(model_pkg) as f:
            package = json.load(f)
        
        # gather existing interface names in the package
        correct_interface_names = set()
        for interface in package["nodePackage"]["interfaces"]:
            correct_interface_names.add( interface["name"] )
        
        # get nodes from graph and get corresponding interface to the model
        # name in model_name
        graph_nodes = _graph['nodeGraph']['nodes']
        
        # lookup interface name by node name
        interface_name = None
        for dicts in graph_nodes:
            if dicts["name"] == name:
                interface_name = dicts["interface"]
                break

        if interface_name is None:
            raise ValueError(
                'Exception Class : ModelClass, Exception Method : __iter__, Exception Message : Model node {} not Found in graph.json'.format(name) )

        folder_name = "{}-{}".format(_c.account_id, interface_name.split('.')[0].split('::')[1])
        name_in_interfaces_pjson = interface_name.split('.')[1]

        if name_in_interfaces_pjson not in correct_interface_names:
            raise ValueError(
                'Exception Class : ModelClass, Exception Method : __iter__, Exception Message : Please use the correct Model interface name: {} not in {}'.format( name_in_interfaces_pjson, correct_interface_names ))

        # read package.json from the folder name we got from the interface,
        # which is in the package folder
        path = './{}/packages/'.format(_c.app_name) + folder_name + '-1.0/' + 'package.json'
        with open(path) as f:
            package = json.load(f)

        interfaces = package["nodePackage"]["interfaces"]
        assets = package["nodePackage"]["assets"]

        # loop thru interfaces to get the asset name of the corresponding
        # interface
        asset_name = None
        for dicts in interfaces:
            if dicts["name"] == name_in_interfaces_pjson:
                asset_name = dicts["asset"]

        if asset_name is None:
            raise ValueError(
                'Exception Class : ModelClass, Exception Method : __iter__, Exception Message : Asset Not Found in package.json interfaces')

        # Instantiate DLRModel
        model_path = _c.models[ name ]  + "-" + _c.compiled_model_suffix
        model = dlr.DLRModel( model_path )
        self._dlr_models[name] = model

    def call( self, input, name, time_out = None ):

        if name not in self._dlr_models:
            self._load_dlr_model(name)

        assert name in self._dlr_models

        dlr_model = self._dlr_models[ name ]
        output = dlr_model.run( input )

        assert isinstance( output, list ), f"Unexpected output type {type(output)}"

        return tuple(output)