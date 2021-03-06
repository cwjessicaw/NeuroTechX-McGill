
# requires python-osc
from pythonosc import osc_message_builder
from pythonosc import udp_client
import plugin_interface as plugintypes
from sklearn.lda import LDA
import time
from scipy import signal
import numpy as np

# Use OSC protocol to broadcast data (UDP layer), using "/openbci" stream. (NB. does not check numbers of channel as TCP server)

class Classifier():
    def __init__(self,
                 start_time,    #start time in seconds
                 channels = [0,1,2],
                 num_trials=3,
                 num_rows=6,
                 num_columns=6,
                 flash=0.2,
                 inter_flash=0.1,
                 inter_mega_trial=3):
        self.column_order = [5, 3, 2, 0, 4, 1, 3, 2, 0, 1, 5, 4, 3, 4, 0, 5, 2, 1]
        self.row_order = [1, 4, 2, 5, 0, 3, 3, 2, 5, 0, 1, 4, 4, 0, 2, 3, 1, 5]
        self.num_rows = num_rows
        self.num_columns = num_columns
        self.lda = LDA()
        self.fs = 250
        self.started = False
        self.collecting = False
        self.buffer = []
        self.data = []
        self.stimulus_time = int((inter_flash + flash) * self.fs)
        self.trial_length = self.stimulus_time * (num_rows + num_columns)
        self.samples_in_data = num_trials * self.trial_length
        self.samples_since_last = 0
        self.num_samples = 0
        self.channels = channels
        self.start_time = start_time
        self.start_index = None
        self.inter_mega_trial = inter_mega_trial
        self.counter = 0
        self.window_length = int(0.6 * 250)
        #print(start_time)
        
        self.lowcut = 0.5
        self.highcut = 20
        
    def add_sample(self, sample):
        self.counter += 1
        if self.collecting:
            self.data.append(sample.channel_data[0:2])
            self.num_samples += 1
            if self.num_samples == self.samples_in_data:
                print(self.counter)
                self.run_prediction()
                self.reset()
        else:
            self.buffer.append(sample.channel_data[0:2])
            self.samples_since_last += 1
            if self.started:
                if self.samples_since_last == self.inter_mega_trial * self.fs:
                    self.collecting = True
                    print(self.counter)
            else: 
                if time.time() > self.start_time:
                    self.started = True
                    self.collecting = True
                    print(self.counter)
    def reset(self):
        self.buffer = self.data[-250*5:]
        self.data = []
        self.samples_since_last = 0
        self.num_samples = 0
        self.collecting = False
    def run_prediction(self,):

        buffer_length = len(self.buffer)
        all_data = np.vstack((np.array(self.buffer), np.array(self.data)))
        filtered_data = self.filter_(all_data)
        REALdata = filtered_data[buffer_length:]    # cut out filtering artifacts/buffer
        print(REALdata.shape)
        data = self.epoch_data(REALdata)
        rows = self.extract(data[::2], row=True)
        columns = self.extract(data[1::2], row=False)
        print(rows.shape)

    def filter_(self,arr):
       nyq = 0.5 * self.fs
       order = 1
       b, a = signal.butter(order, [self.lowcut/nyq, self.highcut/nyq], btype='band')
       for i in range(0, 5):
           arr = signal.lfilter(b, a, arr, axis=0)
       return arr
       
    def epoch_data(self, arr):
        new_arr = []
        i = 0 
        while i <= len(arr) - self.window_length:
            window = arr[i:i+self.window_length].T
            window = np.mean(window, axis=0)
            new_arr.append(window)
            i += self.stimulus_time
        if (i < len(arr)):
            window = arr[i:].T
            window = np.mean(window, axis=0)
            b = np.zeros([self.window_length - len(window)]) # zero pad
            window = np.hstack((window,b))
            new_arr.append(window)
        n = np.array(new_arr)
        print(n.shape)
        return n
    def extract(self, arr, row=True):
        if row:
            order = self.row_order
            num_ = self.num_rows
        else: 
            order = self.column_order
            num_ = self.num_columns
        new_arr = [[] for i in range (0, num_)]
        for i, elem in enumerate(order):
            new_arr[elem].append([arr[i]])
        return np.mean(np.squeeze(np.array(new_arr)), axis=1)



class StreamerOSC(plugintypes.IPluginExtended):
    """

    Relay OpenBCI values to OSC clients

    Args:
      port: Port of the server
      ip: IP address of the server
      address: name of the stream
    """
        
    def __init__(self, ip='localhost', port=12345, address="/openbci"):
        # connection infos
        self.ip = ip
        self.port = port
        self.address = address
        
    # From IPlugin
    def activate(self):
        if len(self.args) > 0:
            self.ip = self.args[0]
        if len(self.args) > 1:
            self.port = int(self.args[1])
        if len(self.args) > 2:
            self.address = self.args[2]
        # init network
        print("Selecting OSC streaming. IP: " + self.ip + ", port: " + str(self.port) + ", address: " + self.address)
        self.client = udp_client.SimpleUDPClient(self.ip, self.port)
        
        self.clf = Classifier(time.time())  #initialize classifier
        print(self.clf.start_time)
    # From IPlugin: close connections, send message to client
    def deactivate(self):
        self.client.send_message("/quit")
        
    # send channels values
    def __call__(self, sample):
        # silently pass if connection drops
        try:
            #print(sample.id)
            self.clf.add_sample(sample)
            self.client.send_message(self.address, sample.channel_data)
        except:
            return

    def show_help(self):
        print("""Optional arguments: [ip [port [address]]]
            \t ip: target IP address (default: 'localhost')
            \t port: target port (default: 12345)
            \t address: select target address (default: '/openbci')""")
