import numpy as np
import pandas as pd
from datetime import datetime
from gurobipy import *

class PrelimExamAssignment():

    def __init__(self,
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

        self.x = self.model.addVars(,vtype=GRB.BINARY, name = "x")
        # Define z(i) indicating the number of rooms prelim i is assigned to
        self.z = self.model.addVars(,vtype=GRB.INTEGER, name = "z")
        # Define p(r,r') to indicate if room r and r' are assigned to the same prelim
        self.index_p = []
        for r in self.rooms:
            for r_prime in self.rooms:
                self.index_p.extend((r,r_prime))
        self.p = self.model.addVars(self.index_p, vtype = GRB.BINARY, name = "p")
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
        for i in range(len(self.exams['exam_id'])):
            #print(self.z.get(i))

            self.model.addConstr(sum(self.x.select(i,'*')), GRB.EQUAL, self.z[i], name = "c0")
        print('add_z_constraint')

        return

    def add_p_constraint(self):
        ''''
        Add constraint to ensure p is 1 iff two rooms are assigned to the same prelim
        '''
        for i in range(len(self.exams['exam_id'])):
            for r in range(len(self.rooms['room_id'])):
                for r_prime in range(len(self.rooms['room_id'])):
                    self.model.addConstr(self.p[r,r_prime] >= self.x[i,r] + self.x[i,r_prime] - 1)
        return

    def add_absolute_room_bound_constraint(self):
        ''''
        Add constraint to ensure a single prelim is assigned to at most R rooms
        '''
        for i in range(len(self.exams['exam_id'])):
            #print(self.z.select(i))
            self.model.addConstr(self.z[i]<= self.R)
        return

    def add_room_use_constraint(self):
        ''''
        Add constraint to ensure each room r is only once
        ''''
        for r in range(len(self.rooms)):
            self.model.addConstr(sum(self.x.select('*',r)), GRB.LESS_EQUAL, 1)
        return

    def add_enrollment_const(self):
        ''''
        Add constraint to ensure each exam is given enough seats (only applies to in person)
        ''''
        for i in range(len(self.exams)):
            self.model.addConstr(sum(self.rooms["capacity"]*self.x[i,'*']), GRB.GREATER_EQUAL,
            self.exams['enrollment'][i])
        return

    def set_objective(self):
        ''''
        Set the objective for the IP
        ''''
        # The objective has terms capturing
        # (1) total number of rooms used
        # (2) distance of rooms to academin org of class
        # (3) squared distances between rooms assigned to the same prelim
        self.model.setObjective( self.rooms_used_weight* quicksum(self.z) + , GRB.MINIMIZE)
        self.model.update()


    def solve(self):
        ''''
        Function to solve the IP problem
        ''''
        # Solve the model
        self.model.optimize()

        return
