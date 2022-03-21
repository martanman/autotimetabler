from functools import reduce
import json
from ortools.sat.python import cp_model
import sys
import time

# special class that can be used to generate ALL the solutions
class VarArraySolutionPrinter(cp_model.CpSolverSolutionCallback):
    """Print intermediate solutions."""

    def __init__(self, variables):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.__variables = variables
        self.__solution_count = 0

    def on_solution_callback(self):
        self.__solution_count += 1
        for v in self.__variables:
            print('%s=%i' % (v, self.Value(v)), end=' ')
            # print()
        print()

    def solution_count(self):
        return self.__solution_count

def timeify(num):
    return f'{int(num // 1)}:{int(num % 1 * 6)}0'


l = [
      [[5, 11, 12], [5, 12, 13]]
    ]


# reduces period data
def redlist(lists):
    l = lists
    if len(l[0]) == 1: # for purely single-period classes
        duration = l[0][0][2] - l[0][0][1]
        return (duration * 2, list(map(lambda il: il[0][0] * 100 + il[0][1] * 2, l)), False)

    if l[0][0][0] == l[0][1][0]: # for classes made of two consecutive periods (we merge into a single period)
        duration = l[0][1][2] - l[0][0][1]
        return (duration * 2, list(map(lambda il: il[0][0] * 100 + il[0][1] * 2, l)), False)

    if l[0][0][1] != l[0][1][0]: # for classes made up of a pair of periods on different days
        duration = (l[0][0][2] - l[0][0][1]) # assumes here that the duration is equivalent for simplicity but should be amended later
        return (duration * 2, list(map(lambda il: tuple(i[0] * 100 + i[1] * 2 for i in il), l)), True)
    
    return [] # if i just missed something

# the main method that does everything
def sols(data):

    gap = int(data['gap']) * 2 if data['gap'] else 0 # minimum break between classes
    mxd = int(data['maxdays']) if data['maxdays'] != '' else len(data['days'])

    newdata = [redlist(l) for l in data['periods']] # reduces data
    """change the above by removing the lambda"""


    Time = time.time()
    model = cp_model.CpModel()

    numCourses = len(newdata)
    normalIter = (i for i in range(numCourses) if not newdata[i][2])
    specialIter = (i for i in range(numCourses) if newdata[i][2])

    classStartTimes = [model.NewIntVarFromDomain(cp_model.Domain.FromValues(newdata[i][1]), 'x%i' %i) for i in normalIter] # start times
    classIntervals = [model.NewFixedSizeIntervalVar(classStartTimes[i], newdata[i][0] + gap, 'xx%i' %i) for i in normalIter] # periods as intervals
    
    for s in specialIter: # handles classes with two periods across multiple days
        duration, specialperiods, _ = newdata[s]
        specPerIter = range(len(specialperiods))
        specialBools = [model.NewBoolVar('e%i'%i) for i in specPerIter] # dummy bools we configure for constraints
        
        # initially set to be 'anything' but will get constrained later by equality
        A = model.NewIntVar(100, 560, 'sA%i')
        B = model.NewIntVar(100, 560, 'sB%i')

        for i in specPerIter:
            model.Add(A == specialperiods[i][0]).OnlyEnforceIf(specialBools[i])
            model.Add(B == specialperiods[i][1]).OnlyEnforceIf(specialBools[i])

        specialIntervalVars = reduce(lambda a, b: a + b, [ \
            [model.NewOptionalFixedSizeIntervalVar(specialperiods[i][0], duration, specialBools[i], 'spi%i'%i),\
            model.NewOptionalFixedSizeIntervalVar(specialperiods[i][1], duration, specialBools[i], 'sPi%i'%i)] \
            for i in specPerIter]) # only one of these will be enforced
        
        model.AddExactlyOne(specialBools) # ensures a single assignment

        # they can now be treated as normal starttimes
        classStartTimes.insert(s, A)
        classStartTimes.append(B)

    daydom = cp_model.Domain.FromValues([int(i) for i in data['days']])

    late = []
    if data['start']:
        earliest = int(data['start']) * 2
        late = [model.NewFixedSizeIntervalVar(i * 100, earliest, 'l%i' %i) for i in range(1, 6)]
    
    nolate = []
    if 'end' in data:
        latest = int(data['end']) * 2 + gap
        nolate = [model.NewFixedSizeIntervalVar(i * 100 + latest, 10, 'l%i' %i) for i in range(1, 6)]
    
    if mxd == 1:
        day = model.NewIntVarFromDomain(daydom, 'day') # within domain of permitted days of the week
        for i in classStartTimes:
            model.AddDivisionEquality(day, i, 100) # makes them all on the same day

    if mxd in [2, 3, 4]:
        Days = [model.NewIntVarFromDomain(daydom, 'day%i'%i) for i in range(len(classStartTimes))] # mon to fri
        dayvars = [model.NewIntVarFromDomain(daydom, 'dv%i'%i) for i in range(mxd)]

        for i in range(len(classStartTimes)):
            model.AddDivisionEquality(Days[i],  classStartTimes[i], 100) # assigns a day

        bools = [[] for _ in range(mxd)]
        for i in range(len(classStartTimes)):
            basename = 'b%i' % i
            for j in range(mxd):
                bools[j].append(model.NewBoolVar(basename + '%i'%j))
                model.Add(Days[i] == dayvars[j]).OnlyEnforceIf(bools[j][i])

        for i in range(len(classStartTimes)):
            model.AddBoolXOr(bools[j][i] for j in range(mxd))

    model.AddNoOverlap(classIntervals + late + nolate + specialIntervalVars) # makes the periods (and other constraints) not overlap

    # solution and printing

    # Create a solver and solve.
    solver = cp_model.CpSolver()

    '''for when you want it to give a solution ↓'''
    status = solver.Solve(model)
    print('elapsed: ' , time.time() - Time)
    print('Status = %s' % solver.StatusName(status))
    if solver.StatusName(status) != 'INFEASIBLE':
        # return [solver.Value(v) for v in classStartTimes] # includes 2nd period of multi-period courses
        return [solver.Value(classStartTimes[i]) for i in range(numCourses)]
    else:
        return None

    '''for when you want it to get all solutions ↓'''
    solution_printer = VarArraySolutionPrinter(classStartTimes)
    # Enumerate all solutions.
    solver.parameters.enumerate_all_solutions = True

    # prints all
    status = solver.Solve(model, solution_printer)

    print('Status = %s' % solver.StatusName(status))
    print('Number of solutions found: %i' % solution_printer.solution_count())


if __name__ == '__main__':
    if len(sys.argv) == 2:
        with open(sys.argv[-1], 'r') as f:
            days = ['na', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri']
            data = json.load(f)
            res = sols(data)
            if res:
                courses = sys.argv[-1][:-5].split('-')
                i = 0
                for day, tim in map(lambda a: (days[a // 100], timeify((a % 100)/2)), res):
                    print(f'{courses[i%len(courses)]} {day} {tim}')
                    i+=1