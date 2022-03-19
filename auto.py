import json
from ortools.sat.python import cp_model
import sys
import time

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


# reduces period data
def redlist(lists):
    newl = []
    for l in lists:
        if len(l) > 1:
            a = l[0]
            b = l[1]
            newl.append([a[0], int(a[1] * 2), int(b[2] * 2)])
        else:
            for i in (1, 2):
                l[0][i] = int(l[0][i] * 2)
                newl.append(l[0])
    
    
    return (newl[0][2] - newl[0][1], list(map(lambda l: l[0] * 100 + l[1], newl)))

def sols(data):

    gap = int(data['gap']) * 2 if data['gap'] else 0 # minimum break between classes

    newdata = list(map(lambda l: redlist(l), data['periods'])) # reduces data

    Time = time.time()
    model = cp_model.CpModel()

    classStartTimes = [model.NewIntVarFromDomain(cp_model.Domain.FromValues(newdata[i][1]), 'x%i' %i) for i in range(len(newdata))] # start times
    classIntervals = [model.NewFixedSizeIntervalVar(classStartTimes[i], newdata[i][0] + gap, 'xx%i' %i) for i in range(len(newdata))] # periods as intervals
    
    daydom = cp_model.Domain.FromValues([int(i) for i in data['days']])

    late = []
    if data['start']:
        earliest = int(data['start']) * 2
        late = [model.NewFixedSizeIntervalVar(i * 100, earliest, 'l%i' %i) for i in range(1, 6)]
    nolate = []
    if 'end' in data:
        latest = int(data['end']) * 2 + gap
        nolate = [model.NewFixedSizeIntervalVar(i * 100 + latest, 3, 'l%i' %i) for i in range(1, 6)]
    
    if data["maxdays"] == '1':
        day = model.NewIntVarFromDomain(daydom, 'day') # mon to fri
        for i in classStartTimes:
            model.AddDivisionEquality(day, i, 100) # makes them all on the same day

    if data["maxdays"] in ['2', '3', '4']:

        mxd = int(data["maxdays"])
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

    model.AddNoOverlap(classIntervals + late + nolate) # makes the periods not overlap

    # solution and printing

    # Create a solver and solve.
    solver = cp_model.CpSolver()

    status = solver.Solve(model)
    print('elapsed: ' , time.time() - Time)
    print('Status = %s' % solver.StatusName(status))
    if solver.StatusName(status) != 'INFEASIBLE':
        return [solver.Value(v) for v in classStartTimes]
    else:
        return None

    '''for when you want it to get all solutions ↓'''

    v = classStartTimes[0]
    return v.Name(), solver.Value(v)

    solution_printer = VarArraySolutionPrinter(classStartTimes)
    # Enumerate all solutions.
    solver.parameters.enumerate_all_solutions = True

    # prints all
    status = solver.Solve(model, solution_printer)
    # prints one
    # print(solver.Value(x), solver.Value(y))

    print('Status = %s' % solver.StatusName(status))
    print('Number of solutions found: %i' % solution_printer.solution_count())


if __name__ == '__main__':
    if len(sys.argv) == 2:
        with open(sys.argv[-1], 'r') as f:
            days = ['na', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri']
            # print(days)
            # exit()
            res = sols(json.load(f))
            if res:
                courses = sys.argv[-1][:-5].split('-')
                i = 0
                for day, tim in map(lambda a: (days[a // 100], timeify((a % 100)/2)), res):
                    print(f'{courses[i]} {day} {tim}')
                    i+=1