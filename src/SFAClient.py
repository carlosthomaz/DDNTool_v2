'''
Created on Mar 22, 2013

@author: xmr
'''

import threading
import time

from SFATimeSeries import SFATimeSeries

from ddn.sfa.api import *

class UnexpectedClientDataException( Exception):
    '''
    Used when the DDN API sent back data that we weren't expecting
    or don't understand.  This is sort of one step up from an
    assert.  Hopefully, we won't use it too often.
    '''
    pass    # don't need anything besides what's already in the base class

    
class SFAClient( threading.Thread):
    '''
    A class that represents a client for the SFA API.  Specifically, each instance will connect to a DDN
    SFA controller and poll it repeatedly for certain data.  The instance will format and pre-process
    the data and make the results available via getter functions.
    '''


    def __init__(self, address, username, password):
        '''
        Constructor
        '''
        threading.Thread.__init__( self, name=address)
        
        self._lock = threading.Lock()
       
        self._address = address 
        self._uri = "https://" + address
        self._user = username
        self._password = password
        
        self._connected = False;
        self._exit_requested = False;

        self._first_pass_complete = False;
        # The values for most everything are empty until the background thread
        # completes a pass through its main loop. 

        
        # How often we poll the DDN hardware - some data needs to be polled
        # faster than others
        # TODO: we probably want to read these values from a config file
        self._fast_poll_interval = 2.0 # in seconds
        self._med_poll_multiple = 15 # multiples of _fast_poll_interval
        self._slow_poll_multiple = 60 # multiples of _fast_poll_interval
        # values of 2.0, 15 & 60 will result in polling every 2 seconds,
        # 30 seconds and 2 minutes for fast, medium and slow, respectively
   
        # Time series data
        # This is a dictionary of dictionaries of SFATimeSeries objects
        # The outer dictionary maps the type of data (ie: vd_read_iops),
        # the inner dictionary maps the actual device number.
        # (We use an inner dictionary instead of a list so the device
        # numbers don't have to be sequential.)
        self._time_series = {}
  
        # Statistics objects
        # We keep copies of each SFAVirtualDiskStatistics and 
        # SFADiskDriveStatistics object (mainly for the I/O latency and
        # request size arrays).
        # Note: _vd_stats is indexed by the LUN number.  _dd_stats is
        # indexed by the disk drive number
        self._vd_stats = {}
        self._dd_stats = {}

        # LUN to virtual disk map
        # The statistics objects deal with virtual disks, but we want to display
        # everything as LUN's.  This maps one to the other.  (It's updated
        # at the medium frequency.)
        self._vd_to_lun = { }


        self.start()    # kick off the background thread
        # We return now, but it's a good idea to wait until is_ready()
        # returns true before attempting to do anything with this object.
        # (The getter functions have undefined (but probably bad) behavior
        # if called before is_ready() returns true.

        
    
    def is_connected(self):
        '''
        Returns True if the instance is connected to the DDN controller, logged in and able
        to communicate with it.
        '''
        return self._connected

    def is_ready(self):
        '''
        Returns True if the instance has enough data for the getter functions to respond
        with meaningful data.  Calling a getter when this function returns false will
        result in undefined (but probably bad) behavior.
        
        Note: The time series average function may still throw an exception even if
        this function returns true, since time series need at least 2 data points
        before they can compute an average.
        '''
        return self._connected and self._first_pass_complete

    
    def stop_thread(self, wait = False, timeout = None):
        '''
        Requests thread to stop and optionally waits for it to do so.
        
        Returns True if the thread has stopped and false if it is still running.
        '''
        self._exit_requested = True;
        
        if wait:
            self.join(timeout)
        
        return ( not self.isAlive())
        
   
    def get_host_name(self):
        '''
        Mostly a convenience function so we can map an object back to a
        human-readable name.
        ''' 
        return self._address

    def get_time_series_names(self):
        '''
        Returns a sorted list of the names of the time series
        '''
        self._lock.acquire()
        try:
            names = sorted(self._time_series)
        finally:
            self._lock.release()

        return names

    def get_lun_nums(self):
        '''
        Returns a sorted list of all the lun numbers this client has
        '''
        self._lock.acquire()
        try:
            luns = sorted(self._vd_to_lun.values())
        finally:
            self._lock.release()

        return luns

    def get_dd_nums(self):
        '''
        Returns a sorted list of all the disk drive indexes on this client has
        '''
        self._lock.acquire()
        try:
            nums = sorted(self._time_series['dd_read_iops'])
        finally:
            self._lock.release()

        return nums


    def get_time_series_average( self, series_name, device_num, span):
        '''
        Return the average value for the specified series and device
        calculated over the specified number of seconds.

        Returns a tuple: first value is the calculated average, second
        value is the actual timespan (in seconds) used to calculate
        the average.
        '''
        #TODO: need some protection against 'key not found' type of
        #errors for both the series name and device number
        self._lock.acquire()
        try:
            average = self._time_series[series_name][device_num].average(span)
        finally:
            self._lock.release() # always release the lock, even if
                                 # an exception occurs above
        return average


    def get_lun_io_read_latencies( self, lun_num):
        '''
        Returns list of I/O read latency values for the specified virtual disk
        '''
        #TODO: need some protection against 'key not found' type of errors 
        self._lock.acquire()
        try:
            latencies = self._vd_stats[lun_num].ReadIOLatencyBuckets
        finally:
            self._lock.release()
        
        return latencies

    def get_lun_io_write_latencies( self, lun_num):
        '''
        Returns list of I/O write latency values for the specified virtual disk
        '''
        #TODO: need some protection against 'key not found' type of errors 
        self._lock.acquire()
        try:
            latencies = self._vd_stats[lun_num].WriteIOLatencyBuckets
        finally:
            self._lock.release()

        return latencies

    def get_lun_io_read_request_sizes( self, lun_num):
        '''
        Returns list of I/O request sizes for the specified virtual disk
        '''
        #TODO: need some protection against 'key not found' type of errors 
        self._lock.acquire()
        try:
            sizes = self._vd_stats[lun_num].ReadIOSizeBuckets
        finally:
            self._lock.release()

        return sizes

    def get_lun_io_write_request_sizes( self, lun_num):
        '''
        Returns list of I/O write request sizes for the specified virtual disk
        '''
        #TODO: need some protection against 'key not found' type of errors 
        self._lock.acquire()
        try:
            sizes = self._vd_stats[lun_num].WriteIOSizeBuckets
        finally:
            self._lock.release()

        return sizes

    def get_dd_io_read_latencies( self, disk_num):
        '''
        Returns list of I/O read latency values for the specified disk drive
        '''
        #TODO: need some protection against 'key not found' type of errors 
        self._lock.acquire()
        try:
            latencies = self._dd_stats[disk_num].ReadIOLatencyBuckets
        finally:
            self._lock.release()

        return latencies

    def get_dd_io_write_latencies( self, disk_num):
        '''
        Returns list of I/O write latency values for the specified disk drive
        '''
        #TODO: need some protection against 'key not found' type of errors 
        self._lock.acquire()
        try:
            latencies = self._dd_stats[disk_num].WriteIOLatencyBuckets
        finally:
            self._lock.release()

        return latencies

    def get_dd_io_read_request_sizes( self, disk_num):
        '''
        Returns list of I/O request sizes for the specified disk drive
        '''
        #TODO: need some protection against 'key not found' type of errors 
        self._lock.acquire()
        try:
            sizes = self._dd_stats[disk_num].ReadIOSizeBuckets
        finally:
            self._lock.release()

        return sizes

    def get_dd_io_write_request_sizes( self, disk_num):
        '''
        Returns list of I/O write request sizes for the specified disk drive
        '''
        #TODO: need some protection against 'key not found' type of errors 
        self._lock.acquire()
        try:
            sizes = self._dd_stats[disk_num].WriteIOSizeBuckets
        finally:
            self._lock.release()

        return sizes


    def get_io_latency_labels( self):
        '''
        Returns the list of labels for the latency values
        '''

        # although the lables don't change much, we still acquire the lock,
        # mainly to avoid issues with an empty self._vd_stats at startup
        self._lock.acquire()
        # We periodically verify that all virtual disks have identical latency labels,
        # so just grab the labels from the first object in the dictionary
        try:
            labels = self._vd_stats[self._vd_stats.keys()[0]].IOLatencyIndexLabels
        finally:
            self._lock.release()
        return labels

    def get_io_size_labels( self):
        '''
        Returns the list of labels for the request size values
        '''

        self._lock.acquire()
        try:
            labels = self._vd_stats[self._vd_stats.keys()[0]].IOSizeIndexLabels
        finally:
            self._lock.release()
        return labels


    def run(self):
        '''
        Main body of the background thread:  polls the SFA, post-processes the data and makes the results
        available to the getter functions.
        '''
       
        self._lock.acquire()
        self._connect()

        # update the lun-to-vd mapping
        # This normally happens at the medium interval, but I need to do it here
        # so that I can store time series data by LUN instead of by virtual disk
        self._update_lun_map()

        # initialize the time series arrays
        vd_stats = SFAVirtualDiskStatistics.getAll()
        self._time_series['lun_read_iops'] = { }
        self._time_series['lun_write_iops'] = { }
        self._time_series['lun_transfer_bytes'] = { }
        self._time_series['lun_forwarded_bytes'] = { }
        self._time_series['lun_forwarded_iops'] = { }
        for stats in vd_stats:
            index = stats.Index
            self._vd_stats[index] = stats

            # Note that these maps are indexed by Lun, not by virtual disk (despite
            # coming from SFAVirtualDiskStatistics objects)
            # 300 entries is 10 minutes of data at 2 second sample rate
            self._time_series['lun_read_iops'][self._vd_to_lun[index]] = SFATimeSeries( 300) 
            self._time_series['lun_write_iops'][self._vd_to_lun[index]] = SFATimeSeries( 300)
            self._time_series['lun_transfer_bytes'][self._vd_to_lun[index]] = SFATimeSeries( 300)
            self._time_series['lun_forwarded_bytes'][self._vd_to_lun[index]] = SFATimeSeries( 300)
            self._time_series['lun_forwarded_iops'][self._vd_to_lun[index]] = SFATimeSeries( 300)

        disk_stats = SFADiskDriveStatistics.getAll()
        self._time_series['dd_read_iops'] = { }
        self._time_series['dd_write_iops'] = { }
        self._time_series['dd_transfer_bytes'] = { }
        for stats in disk_stats:
            index = stats.Index
            self._dd_stats[index] = stats
            self._time_series['dd_read_iops'][index] = SFATimeSeries( 300)
            self._time_series['dd_write_iops'][index] = SFATimeSeries( 300)
            self._time_series['dd_transfer_bytes'][index] = SFATimeSeries( 300)

        self._lock.release()

        # verify the IO request size and latency labels are what we expect (and have
        # hard coded into the database column headings)

        expected_size_labels = ['IO Size <=4KiB', 'IO Size <=8KiB', 'IO Size <=16KiB',
                'IO Size <=32KiB', 'IO Size <=64KiB', 'IO Size <=128KiB',
                'IO Size <=256KiB', 'IO Size <=512KiB', 'IO Size <=1MiB',
                'IO Size <=2MiB', 'IO Size <=4MiB', 'IO Size >4MiB']
        expected_lun_latency_labels = ['Latency Counts <=16ms', 'Latency Counts <=32ms',
                'Latency Counts <=64ms', 'Latency Counts <=128ms', 'Latency Counts <=256ms',
                'Latency Counts <=512ms','Latency Counts <=1s', 'Latency Counts <=2s',
                'Latency Counts <=4s', 'Latency Counts <=8s', 'Latency Counts <=16s',
                'Latency Counts >16s']
        expected_dd_latency_labels = ['Latency Counts <=4ms', 'Latency Counts <=8ms',
                'Latency Counts <=16ms', 'Latency Counts <=32ms', 'Latency Counts <=64ms',
                'Latency Counts <=128ms', 'Latency Counts <=256ms', 'Latency Counts <=512ms',
                'Latency Counts <=1s', 'Latency Counts <=2s', 'Latency Counts <=4s',
                'Latency Counts >4s']


        for stats in vd_stats:
            if stats.IOSizeIndexLabels != expected_size_labels:
                raise UnexpectedClientDataException(
                        "Unexpected IO size index labels for %s virtual disk %d" % \
                                (self.get_host_name(), stats.Index))
            if stats.IOLatencyIndexLabels != expected_lun_latency_labels:
                raise UnexpectedClientDataException(
                        "Unexpected IO latency index labels for %s virtual disk %d" % \
                                (self.get_host_name(), stats.Index))
        for stats in disk_stats:
            if stats.IOSizeIndexLabels != expected_size_labels:
                raise UnexpectedClientDataException(
                        "Unexpected IO size index labels for %s disk drive %d" % \
                                (self.get_host_name(), stats.Index))
            if stats.IOLatencyIndexLabels != expected_dd_latency_labels:
                raise UnexpectedClientDataException(
                        "Unexpected IO latency index labels for %s disk drive %d" % \
                                (self.get_host_name(), stats.Index))

  
        next_fast_poll_time = 0
        fast_iteration = -1
        
        while not self._exit_requested:  # loop until we're told not to
            
            while (time.time() < next_fast_poll_time):
                time.sleep(self._fast_poll_interval / 10) # wait for the poll time to come up
            
            next_fast_poll_time = time.time() + self._fast_poll_interval
            fast_iteration += 1
            
            ############# Fast Interval Stuff #######################

            ##Virtual Disk Statistics 
            vd_stats = SFAVirtualDiskStatistics.getAll()
            try:
                self._lock.acquire()  # need to lock the mutex before we modify the data series
                self._vd_stats = { } # erase the old _vd_stats dictionary
                for stats in vd_stats:
                    index = stats.Index

                    # Save the entire object (mainly for its I/O latency and request
                    # size arrays
                    self._vd_stats[self._vd_to_lun[index]] = stats
                    
                    # Note: we actually get back 2 element lists - one element
                    # for each controller in the couplet.  In theory, one of those
                    # elements should always be 0.
                    self._time_series['lun_read_iops'][self._vd_to_lun[index]].append(stats.ReadIOs[0] + stats.ReadIOs[1])
                    self._time_series['lun_write_iops'][self._vd_to_lun[index]].append(stats.WriteIOs[0] + stats.WriteIOs[1])
                    self._time_series['lun_transfer_bytes'][self._vd_to_lun[index]].append(
                            (stats.KBytesTransferred[0] + stats.KBytesTransferred[1]) * 1024)
                    # Note: converted to bytes

                    self._time_series['lun_forwarded_bytes'][self._vd_to_lun[index]].append(
                            (stats.KBytesForwarded[0] + stats.KBytesForwarded[1]) * 1024)
                    # Note: converted to bytes 

                    self._time_series['lun_forwarded_iops'][self._vd_to_lun[index]].append(
                            stats.ForwardedIOs[0] + stats.ForwardedIOs[1])
            finally:
                self._lock.release()

            # Yes - deliberately unlocking & re-locking the mutex to give other
            # threads a chance to access the data

            ##Disk Statistics
            disk_stats = SFADiskDriveStatistics.getAll()
            try:
                self._lock.acquire()  # need to lock the mutex before we modify the data series
                for stats in disk_stats:
                    index = stats.Index

                    # Note: we actually get back 2 element lists - one element
                    # for each controller in the couplet.  In theory, one of those
                    # elements should always be 0.
                    self._time_series['dd_read_iops'][index].append(stats.ReadIOs[0] + stats.ReadIOs[1])
                    self._time_series['dd_write_iops'][index].append(stats.WriteIOs[0] + stats.WriteIOs[1])
                    self._time_series['dd_transfer_bytes'][index].append(
                            (stats.KBytesTransferred[0] + stats.KBytesTransferred[1]) * 1024)
                    # Note: converted to bytes

            finally:
                self._lock.release()
            
            ############# Medium Interval Stuff #####################
            if (fast_iteration % self._med_poll_multiple == 0):
                # Update the LUN to virtual disk map.  (We probably don't
                # need to do this very often, but it's not a lot of work
                # and if an admin ever makes any changes, they'll show up
                # fairly quickly
                self._update_lun_map()
            
            ############# Slow Interval Stuff #######################
            if (fast_iteration % self._slow_poll_multiple == 0):
                # TODO: implement slow interval stuff
                pass

            self._first_pass_complete = True    
        # end of main while loop
    # end of run() 
            
    # other getters we're going to want:
    # - rebuild and verify bandwidth (not available in the API yet)
    # - "Tier Delay"  - no such command in the API.  Will have to compute it from other values
    # 
     
     
    def _connect(self):
        '''
        Log in to the DDN hardware
        '''
        try:
            APIConnect( self._uri, (self._user, self._password))
            # Note: this will throw an exception if it can't connect
            # Known exceptions:
            # ddn.sfa.core.APIContextException: -2: Invalid username and/or password
            # pywbem.cim_operations.CIMError: (0, 'Socket error: [Errno -2] Name or service not known')
            self._connected = True;
        except APIContextException, e:
            pass
        #except CIMError, e:
        #    pass
        
    def _update_lun_map( self):
        presentations = SFAPresentation.getAll()
        for p in presentations:
            self._vd_to_lun[p.VirtualDiskIndex] = p.LUN


