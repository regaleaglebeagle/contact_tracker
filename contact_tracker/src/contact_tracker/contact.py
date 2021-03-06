#!/usr/bin/env python
# Class to create a Contact object and initialize its
# associated Kalman filters.

# Author: Rachel White
# University of New Hampshire
# Last Modified: 03/20/2020


#import rospy
import numpy as np
import math

#from filterpy.kalman import KalmanFilter
#from filterpy.kalman import update
#from filterpy.kalman import predict
from filterpy.kalman import IMMEstimator
#from filterpy.common import Q_discrete_white_noise
from filterpy.common import Q_continuous_white_noise


class Contact:
    """
    Class to create contact object with its own Kalman filter bank.
    """

    def __init__(self, detect_info, all_filters, timestamp):
        """
        Define the constructor.
        
        detect_info -- dictionary containing data from the detect message being used to create this contact
        all_filters -- list containing unique KalmanFilter objects for this specific contact object
        timestamp -- header from the detect message 
        """

        # Variables for the IMM Estimator
        self.mu = np.array([0.3, 0.7])
        self.M = np.array([[0.3, 0.7],
                           [0.95, 0.05]])
        self.M = np.array([[0.5, 0.5],
                           [0.5, 0.5]])

        '''self.mu = np.array([0.5, 0.5])
        self.M = np.array([[0.5, 0.5],
                           [0.5, 0.5]])'''
        # all_filters is purely for initializing the filters
        self.all_filters = all_filters 

        
        # Variables the define the piecewise continuous white noise variance
        # model for 1st and 2nd order filters. Units are m^2/s^3 and characterize
        # both how much the uncertainty grows with each predict but also how
        # much the estimate is allowed to change with each step. 
        self.vel_var = .5
        self.acc_var = .1
       
        # Variables that keep track of time
        self.dt = 1.0 
        self.last_measured = detect_info['header'].stamp
        self.last_xpos = .0
        self.last_ypos = .0
        self.last_xvel = .0
        self.last_yvel = .0

        # Variables that keep track of data for plotting purposes
        self.xs = []
        self.zs = []
        self.ps = []
        self.times = []
        
        # Other important variables
        self.info = detect_info
        self.id = timestamp 
        self.Z = None
        
        # Initialize the filters and setup the IMM Estimator
        self.init_filters()
        self.filter_bank = IMMEstimator(all_filters, self.mu, self.M)

        
        # Process noise model uncertainty. 
        #self.constantVelocity_VAR = 0.5**2
        #self.constantAcceleration_VAR = 0.1**2

    def set_Q(self):
        """
        Recompute the value of Q for the Kalman filters in this contact.

        Keyword arguments:
        contact -- contact object for which to recompute Q
        """
        
        for kf in self.all_filters:
            if kf.filter_type == 'first': 
                # All Q matrices have to have matching dimensions (6x6 in our case).
                # So we have to zero-pad the Q matrix of the constant velocity filter
                # as it is naturally a 4x4.
                empty_array = np.zeros([6, 6])
                #noise = Q_discrete_white_noise(dim=2, var=self.vel_var, dt=contact.dt, block_size=2, order_by_dim=False) 
                noise = Q_continuous_white_noise(dim=2, 
                                                 spectral_density=self.vel_var,
                                                 dt=self.dt,
                                                 block_size=2,
                                                 order_by_dim=False)
                empty_array[:noise.shape[0],:noise.shape[1]] = noise  
                kf.Q = empty_array
            
            elif kf.filter_type == 'second':
                #kf.Q = Q_discrete_white_noise(dim=3, var=self.acc_var, dt=contact.dt, block_size=2, order_by_dim=False) 
                kf.Q = Q_continuous_white_noise(dim=3,
                                                spectral_density=self.acc_var,
                                                dt=self.dt,
                                                block_size=2,
                                                order_by_dim=False)

    def init_filters(self):
        """
        Initialize each filter in this contact's filter bank.
        """
        
        

        
        for i in range(0, len(self.all_filters)):
            
            if not math.isnan(self.info['x_pos']) and math.isnan(self.info['x_vel']):
                print('Instantiating ', self.all_filters[i].filter_type, ' Kalman filter with position but without velocity')
                self.all_filters[i].x = np.array([self.info['x_pos'], self.info['y_pos'], .0, .0, .0, .0]).T
                self.all_filters[i].F = np.array([
                    [1., .0, self.dt, .0, 0.5*self.dt**2, .0],
                    [.0, 1., .0, self.dt, .0, 0.5*self.dt**2],
                    [.0, .0, 1., .0, self.dt, .0],
                    [.0, .0, .0, 1., .0, self.dt],
                    [.0, .0, .0, .0, .0, .0],
                    [.0, .0, .0, .0, .0, .0]])

                
                '''
                # All Q matrices have to have matching dimensions (6x6 in our case).
                # So we have to zero-pad the Q matrix of the constant velocity filter
                # as it is naturally a 4x4.
                empty_array = np.zeros([6, 6])
                
                # And the process noise variance/time is different for first
                # and second order filters, since the variance here is that of 
                # a zero velocity and zero velocity acceleration model respectively. 
                if self.all_filters[i].filter_type == 'first':
                    noise = Q_continuous_white_noise(dim=2, 
                                                   spectral_density= self.all_filters[i].R, 
                                                   dt=self.dt, 
                                                   block_size=2, 
                                                   order_by_dim=False)
                elif self.all_filters[i].filter_type == 'second':
                    noise = Q_continuous_white_noise(dim=2, 
                                                   spectral_density= self.constantAcceleration_VAR, 
                                                   dt=self.dt, 
                                                   block_size=2, 
                                                   order_by_dim=False)
                    
                empty_array[:noise.shape[0],:noise.shape[1]] = noise  
                self.all_filters[i].Q = empty_array
                '''
            
            elif not math.isnan(self.info['x_pos']) and not math.isnan(self.info['x_vel']):
                print('Instantiating ', self.all_filters[i].filter_type, ' order Kalman filter with velocity and position')
                self.all_filters[i].x = np.array([self.info['x_pos'], self.info['y_pos'], self.info['x_vel'], self.info['y_vel'], .0, .0]).T
                self.all_filters[i].F = np.array([
                    [1., .0, self.dt, .0, 0.5*self.dt**2, .0],
                    [.0, 1., .0, self.dt, .0, 0.5*self.dt**2],
                    [.0, .0, 1., .0, self.dt, .0],
                    [.0, .0, .0, 1., .0, self.dt],
                    [.0, .0, .0, .0, 1., .0],
                    [.0, .0, .0, .0, .0, 1.]])

            '''
                # And the process noise variance/time is different for first
                # and second order filters, since the variance here is that of 
                # a zero velocity and zero velocity acceleration model respectively. 
                if self.all_filters[i].filter_type == 'first':
                    noise = Q_discrete_white_noise(dim=3, var = self.constantVelocity_VAR, 
                                                   dt=self.dt, block_size=2, order_by_dim=False)
                elif self.all_filters[i].filter_type == 'second':
                    noise = Q_discrete_white_noise(dim=3, var = self.constantAcceleration_VAR, 
                                                   dt=self.dt, block_size=2, order_by_dim=False)
            '''
            
            self.set_Q()            
            
            # Define the state covariance matrix.
            self.all_filters[i].P = np.array([
                [100.0*self.info['pos_covar'][0], .0, .0, .0, .0, .0],
                [.0, 100.0*self.info['pos_covar'][6], .0, .0, .0, .0],
                [.0, .0, 5.0**2, .0, .0, .0],
                [.0, .0, .0, 5.0**2, .0, .0],
                [.0, .0, .0, .0, 1.**2, .0],
                [.0, .0, .0, .0, .0, 1.**2]])


    def set_Z(self, detect_info):
        """
        Set the measurement vector based on information sent in the detect message.

        Keyword arguments:
        detect_info -- the dictionary containing the detect info being checked
        """
        
        '''
        if math.isnan(detect_info['x_pos']):
            self.Z = [self.last_xpos, self.last_ypos, self.info['x_vel'], self.info['y_vel']]
        
        elif math.isnan(detect_info['x_vel']):
            self.Z = [self.info['x_pos'], self.info['y_pos'], self.last_xvel, self.last_yvel]
        
        else:
            self.Z = [self.info['x_pos'], self.info['y_pos'], self.info['x_vel'], self.info['y_vel']]
        '''
        
        if math.isnan(detect_info['x_vel']):
            self.Z = [self.info['x_pos'], self.info['y_pos']]
        
        else:
            self.Z = [self.info['x_pos'], self.info['y_pos'], self.info['x_vel'], self.info['y_vel']]
  
 




