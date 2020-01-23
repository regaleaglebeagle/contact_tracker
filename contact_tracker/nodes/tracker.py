#!/usr/bin/env python

# A contact is identifed by position, not id, and is
# independent of the sensor that produced it.

# Author: Rachel White
# University of New Hampshire
# Date last modified: 01/15/2020

import math
import time
import rospy
import datetime
import numpy as np
import matplotlib.pyplot as plt

import contact_tracker.contact
from marine_msgs.msg import Detect

from filterpy.kalman import KalmanFilter
from filterpy.kalman import update
from filterpy.kalman import predict
from filterpy.common import Q_discrete_white_noise

from dynamic_reconfigure.server import Server
from contact_tracker.cfg import contact_trackerConfig

DEBUG = True


class KalmanTracker:
    """
    Class to create custom Kalman filter.
    """


    def __init__(self):
        """
        Define the constructor.

        max_time -- amount of time that must ellapse before an item is deleted from all_contacts
        dt -- time step for the Kalman filters
        initial_velocity -- velocity at the start of the program
        """

        self.all_contacts = {}


    def plot_x_vs_y(self):
        """
        Visualize results of the Kalman filter by plotting the measurements against the 
        predictions of the Kalman filter.
        """

        c = self.all_contacts[1]
        
        m_xs = []
        m_ys = []
        p_xs = []
        p_ys = []

        print('PRINTING MEASUREMENTS')
        for i in c.zs:
            print(i)
            m_xs.append(i[0])
            m_ys.append(i[1])
        
        print('PRINTING PREDICTIONS')
        for i in c.xs:
            print(i)
            p_xs.append(i[0])
            p_ys.append(i[1])

        plt.scatter(m_xs, m_ys, linestyle='-', label='measurements', color='y')
        plt.plot(p_xs, p_ys, label='predictions', color='b')
        plt.legend()
        plt.xlabel('x position')
        plt.ylabel('y position')
        plt.xlim(c.xs[0][0], 300)
        plt.ylim(c.xs[0][0], 300)
        plt.show()


    def plot_x_vs_time(self):
        """
        Visualize results of the Kalman filter by plotting the measurements against the 
        predictions of the Kalman filter.
        """

        c = self.all_contacts[1]
        
        m_xs = []
        p_xs = []

        for i in c.zs:
            m_xs.append(i[0])
        
        for i in c.xs:
            p_xs.append(i[0])
 
        print('PRINTING TIMES')
        for i in c.times:
            print(i)


        plt.scatter(c.times, m_xs, linestyle='-', label='measurements', color='y')
        plt.plot(c.times, p_xs, label='predictions', color='b')
        plt.legend()
        plt.xlabel('time')
        plt.ylabel('x position')
        plt.ylim(c.xs[0][0], 300)
        plt.show()

    
    def dump(self, detect_info):
        """
        Print the contents of a contact's detect_info dictionary for debugging purposes.
        """
        
        print('+++++++ CONTACTS +++++++')
        for k, v in detect_info.items():
            print(k, v)


    def reconfigure_callback(self, config, level):
        """
        Get the parameters from the cfg file and assign them to the member variables of the 
        KalmanTracker class.
        """

        self.qhat = config['qhat']
        self.max_time = config['max_time']
        self.initial_velocity = config['initial_velocity']
        self.variance = config['variance']
        return config


    def callback(self, data):
        """
        Listen for detects and add to dictionary and filter if not already there.

        Keyword arguments:
        data -- the Detect message transmitted
        """
        
        ####################################
        ####### INITIALIZE VARIABLES #######
        ####################################

        # Get necessary info from the Detect data
        detect_info = {
                'header': data.header,
                'sensor_id': data.sensor_id,
                'pos_seq': data.p.header.seq,
                'twist_seq': data.t.header.seq,
                'pos_stamp': data.p.header.stamp,
                'twist_stamp': data.t.header.stamp,
                'pos_frame_id': data.p.header.frame_id,
                'twist_frame_id': data.t.header.frame_id,
                'pos_covar': data.p.pose.covariance,
                'twist_covar': data.t.twist.covariance,
                'x_pos': float('nan'),
                'x_vel': float('nan'),
                'y_pos': float('nan'),
                'y_vel': float('nan'),
                'z_pos': float('nan'),
                'z_vel': float('nan')
                }
        
        print(data)

        # Assign values only if they are not NaNs
        if not math.isnan(data.p.pose.pose.position.x):
            if DEBUG: print('x_pos not a nan')
            detect_info['x_pos'] = float(data.p.pose.pose.position.x)

        if not math.isnan(data.p.pose.pose.position.y):
            if DEBUG: print('y_pos not a nan')
            detect_info['y_pos'] = float(data.p.pose.pose.position.y)

        if not math.isnan(data.p.pose.pose.position.z):
            if DEBUG: print('z_pos not a nan')
            detect_info['z_pos'] = float(data.p.pose.pose.position.z)

        if not math.isnan(data.t.twist.twist.linear.x):
            if DEBUG: print('x_vel not a nan')
            detect_info['x_vel'] = float(data.t.twist.twist.linear.x)

        if not math.isnan(data.t.twist.twist.linear.y):
            if DEBUG: print('y_vel not a nan')
            detect_info['y_vel'] = float(data.t.twist.twist.linear.y)

        if not math.isnan(data.t.twist.twist.linear.z):
            if DEBUG: print('z_vel not a nan')
            detect_info['z_vel'] = float(data.t.twist.twist.linear.z)


        # Check to see that if one coordinate is not NaN, neither is the other
        if ((not math.isnan(detect_info['x_pos']) and math.isnan(detect_info['y_pos'])) or (math.isnan(detect_info['x_pos']) and not math.isnan(detect_info['y_pos']))):
            if DEBUG: print('ERROR: x_pos and y_pos both were not nans...returning')
            return 
        if ((not math.isnan(detect_info['x_vel']) and math.isnan(detect_info['y_vel'])) or (math.isnan(detect_info['x_vel']) and not math.isnan(detect_info['y_vel']))):
            if DEBUG: print('ERROR: x_vel and y_vel both were not nans...returning')
            return 
        
        if DEBUG:
            contact_id = 1
        else:    
            contact_id = (detect_info['x_pos'], detect_info['y_pos']) # TODO: Refine this to account for movement in the contact


        #######################################################
        ####### CREATE OR UPDATE CONTACT WITH VARIABLES #######
        #######################################################

        # Create new contact object.
        epoch = 0
        if not contact_id in self.all_contacts:
          
            kf = None
            c = None
            start_time = time.time()
            
            if not math.isnan(detect_info['x_pos']) and math.isnan(detect_info['x_vel']):
                rospy.loginfo('Instantiating first-order Kalman filter with position but without velocity')
                kf = KalmanFilter(dim_x=4, dim_z=2)
                c = contact_tracker.contact.Contact(detect_info, kf, self.variance, start_time, contact_id)
                c.init_kf_with_position_only()
            
            elif math.isnan(detect_info['x_pos']) and not math.isnan(detect_info['x_vel']):
                rospy.loginfo('Instantiating first-order Kalman filter with velocity but without position')
                kf = KalmanFilter(dim_x=4, dim_z=2)
                c = contact_tracker.contact.Contact(detect_info, kf, self.variance, start_time, contact_id)
                c.init_kf_with_velocity_only()
            
            elif not math.isnan(detect_info['x_pos']) and not math.isnan(detect_info['x_vel']):
                rospy.loginfo('Instantiating first-order Kalman filter with velocity and position')
                kf = KalmanFilter(dim_x=4, dim_z=4)
                c = contact_tracker.contact.Contact(detect_info, kf, self.variance, start_time, contact_id)
                c.init_kf_with_position_and_velocity()
            
            '''elif not math.isnan(detect_info['x_acc']):
                rospy.loginfo('Instantiating second-order Kalman filter')
                kf = KalmanFilter(dim_x=6, dim_z=4)
                c = contact_tracker.contact.Contact(detect_info, kf, self.variance, start_time, contact_id)
                c.init_kf_with_acceleration()'''

            # Add this new object to all_contacts
            self.all_contacts[contact_id] = c

        else:
            # Recompute the value for dt, and use it to update this Contact's KalmanFilter's Q.
            # Then update the time stamp for when this contact was last accessed so we know not
            # to remove it anytime soon. 
            c = self.all_contacts[contact_id]
            c.last_accessed = time.time()
            epoch = c.last_accessed - c.first_accessed
            c.dt = epoch
            c.kf.Q = Q_discrete_white_noise(dim=4, dt=epoch*self.qhat, var = 0.04**2) #TODO: Figure out what the variance should be here.
            c.info = detect_info
            rospy.loginfo(self.qhat)

        # Add to self.kalman_filter
        rospy.loginfo('Calling predict() and update()')
        c = self.all_contacts[contact_id]
        c.kf.predict()
        if c.kf.dim_z == 4:
            c.kf.update((c.info['x_pos'], c.info['y_pos'], c.info['x_vel'], c.info['y_vel']))
        else:
            c.kf.update((c.info['x_pos'], c.info['y_pos']))
        
        # Append appropriate prior and measurements to lists here
        c.xs.append(c.kf.x)
        c.zs.append(c.kf.z)
        c.times.append(epoch)

        # Remove items from the dictionary that have not been accessed in a while
        '''for contact_id in self.all_contacts:
            cur_contact = self.all_contacts[contact_id]
            if int(timestamp.second / 60) - int(cur_contact.last_accessed.second / 60) > MAX_TIME:
                del self.all_contacts[cur_contact]'''


    def run(self):
        """
        Initialize the node and set it to subscribe to the detects topic.
        """

        rospy.init_node('tracker', anonymous=True)
        srv = Server(contact_trackerConfig, self.reconfigure_callback)
        rospy.Subscriber('/detects', Detect, self.callback)
        rospy.spin()

        if DEBUG:
            rospy.loginfo('plotting the results')
            #self.plot_x_vs_y()
            self.plot_x_vs_time()


if __name__=='__main__':

    try:
        kt = KalmanTracker()
        kt.run()

    except rospy.ROSInterruptException:
        rospy.loginfo('Falied to initialize KalmanTracker')
        pass
