import numpy as np
import pandas as pd
from datetime import datetime
from gurobipy import *

class PrelimExamAssignment():

    def __init__(self,
                room_label_dict,
                 exams,
                 exam_dates,
                 rooms,
                 acadorg_dist,
                 dist,
                 wr = 1,
                 w_ac = 0.05,
                 R = 10):
        '''
        Inputs:
        - exams: dataframe with each prelim that must be scheduled. Should have the following fields:
            - exam_id: the unique id for this prelim
            - enrollment: the enrollment for this course
            - modality: Online/In Pesron exam
            - course: course name
            - acadorg: academic organization the course belongs to
            - d,k: the time slot where this prelim should be scheduled
        - exam_dates: dictionary of date -> date_index

        - rooms: dataframe with each room that can host a prelim. Should have the following fields:
            - id: the unique id for this room
            - building: the building where this room is located
            - room_num: the room number of this room
            - capacity: the capacity of this room subject to COVID-19 social distancing
        - acadorg_dist: a dataframe with the distance from an acadorg to any building
        - dist: a dataframe with the distance from any building to another
        - R: the maximum number of rooms a single prelim can occupy
        '''

        # save parameters
        self.room_label_dict = room_label_dict
        self.exam_dates = exam_dates
        self.R = R
        self.wr = wr
        self.w_ac = w_ac

        # set up exams dataframe
        self.exams = exams.rename(columns={"enrollment": "n"})
        self.exams.loc[self.exams.modality == 'Online','n'] = 0 # set enrollment of online classes to 0
        self.M = len(self.exams)

        # set up rooms dataframe and add a dummy room for the online exams
        self.rooms = (rooms.rename(columns={"capacity": "s"})
                           .assign(b = 1)
                           .append(pd.DataFrame([{"room_id" : "dummy",
                                                  "building" : "dummy",
                                                  "s" : 0,
                                                  "b" : self.M}]))
                           .reset_index().drop(columns=['index']))[['room_id','building', 'room', 's', 'b']]
        self.N = len(self.rooms)

        # add dummy building to distance matrix
        self.acadorg_dist = acadorg_dist
        self.acadorg_dist['dummy'] = 0.0

        # add dummy buildings to buidling to building distance matrix
        self.dist = dist
        self.dist['dummy'] = 0.0
        self.dist = self.dist.append(pd.Series(0, index=self.dist.columns), ignore_index=True)
        self.dist.index = self.dist.columns


    def build_model(self):
        '''
        Function that creates the IP model
        '''
        self.model = Model("ip_1")

        # initialize the decision variables
        self.init_dv()
        self.model.update()
        #Add constraints
        self.add_constraints()
        self.model.update()
        #Set Objective
        self.set_objective()

    def init_dv(self):
        '''
        Defines the decision variables
        '''
        # Define x(i,r) indicating if prelim i is assigned to room r
        self.index_x = []
        for i in self.exams['exam_id']:
            for r in self.rooms['room_id']:
                self.index_x.append((i,r))

        self.x = self.model.addVars(self.index_x,vtype=GRB.BINARY, name = "x")
        # Define z(i) indicating the number of rooms prelim i is assigned to
        self.index_z = []
        for i in self.exams['exam_id']:
            self.index_z.append((i))
        self.z = self.model.addVars(self.index_z,vtype=GRB.INTEGER, name = "z")
        # Define p(r,r') to indicate if room r and r' are assigned to the same prelim
        self.index_p = []
        room_ids = self.rooms['room_id']
        for i in range(len(self.rooms['room_id'])):
            for j in range(len(self.rooms['room_id'])):

                self.index_p.append((room_ids[i],room_ids[j]))

        self.p = self.model.addVars(self.index_p, vtype = GRB.BINARY, name = "p")
        #print(self.index_x)
        #print(self.index_z)
        #print(self.index_p)
    def add_constraints(self):
        '''
        Function to add all the constraints
        '''
        self.add_z_constraint()
        self.add_p_constraint()
        self.add_absolute_room_bound_constraint()
        self.add_room_use_constraint()
        self.add_enrollment_const()

    def add_z_constraint(self):
        '''
        Add constraint to ensure z represents the number of classes a prelim is assigned to
        '''
        for i in self.exams['exam_id']:
            #print(self.z.get(i))
            #print(len(self.x.select(i,'*')))
            self.model.addConstr(sum(self.x.select(i,'*')), GRB.EQUAL, self.z[i], name = "c0")
        print('add_z_constraint')

        return

    def add_p_constraint(self):
        ''''
        Add constraint to ensure p is 1 iff two rooms are assigned to the same prelim
        '''
        room_ids = self.rooms['room_id']
        for i in self.exams['exam_id']:
            for j in range(len(self.rooms['room_id'])):
                r = self.rooms['room_id'][j]
                for k in range(len(self.rooms['room_id'])):
                    r_prime = self.rooms['room_id'][k]
                    self.model.addConstr(self.p[r,r_prime] >= self.x[i,r] + self.x[i,r_prime] - 1)
        print('add_p_constraint')
        return

    def add_absolute_room_bound_constraint(self):
        ''''
        Add constraint to ensure a single prelim is assigned to at most R rooms
        '''
        for i in self.exams['exam_id']:
            #print(self.z.select(i))
            self.model.addConstr(self.z[i]<= self.R)
        print('add_absolute_room_bound_constraint')
        return

    def add_room_use_constraint(self):
        ''''
        Add constraint to ensure each room r is only once
        '''

        for i in range(len(self.rooms['room_id'])):
            r = self.rooms['room_id'][i]
            self.model.addConstr(sum(self.x.select('*',r)), GRB.LESS_EQUAL, 1)
        print('add_room_use_constraint')
        return

    def add_enrollment_const(self):
        ''''
        Add constraint to ensure each exam is given enough seats (only applies to in person)
        '''
        exams = self.exams.reset_index(drop = True)
        for idx,exam_i in enumerate(exams['exam_id']):
                   self.model.addConstr(sum(self.rooms["s"])*sum(self.x.select(exam_i,'*')), GRB.GREATER_EQUAL,exams['n'][idx])
        print('add_enrollment_const')
        return

    def set_objective(self):
        ''''
        Set the objective for the IP
        '''
        # The objective has terms capturing
        # (1) total number of rooms used
        # (2) distance of rooms to academin org of class
        # (3) squared distances between rooms assigned to the same prelim
        
        academic_org_dist = []
        #second summation in the objective
        for room in self.acadorg_dist.columns:
            #get each distance from the room
            for dist_aca in self.acadorg_dist[room]:
                #get exam id
                for i in self.exams['exam_id']:
                    #map to room index
                    room_id_list = self.room_label_dict[room]
                    for true_id in room_id_list:
                        #add constraint to list
                        unit = self.x[i,true_id]*dist_aca*self.w_ac
                        academic_org_dist.append(unit)

        squared_dist_constraint = []
        for r in self.dist.columns:
            for distance in self.dist[r]:
                room_id_list = self.room_label_dict[r]
                for r_true_id in room_id_list:
                    unit = (distance**2)*sum(self.p.select(r_true_id ,'*'))
                    squared_dist_constraint.append(unit)

        self.model.setObjective(self.wr*quicksum(self.z) + sum(squared_dist_constraint) + sum(academic_org_dist), GRB.MINIMIZE)
       
        self.model.update()


    def solve(self):
        ''''
        Function to solve the IP problem
        '''
        # Solve the model
        self.model.optimize()
        x_vars_with_value_1 = []

        for result in self.x:
            if 'value 1.0' in str(self.x[result]):
                x_vars_with_value_1.append(result)

        return x_vars_with_value_1
