#!/usr/bin/env python3
# Copyright (c) 2012 Sven Hertle <sven.hertle@googlemail.com>

__version__="2.0a"

import sys
import subprocess
import json
import re
import datetime
import argparse

#
# Calculations
#

class Calculator:
    printer = None
    task_cmd = "task"
    print_null = False
    print_full = False
    project = None
    excl_projs = []

    def __init__(self):
        self.printer = ReadablePrinter()

    def setPrinter(self, printer):
        self.printer = printer

    def setTaskCmd(self, task_cmd):
        self.task_cmd = task_cmd
    
    def setPrintNull(self):
        self.print_null = True

    def setPrintFull(self):
        self.print_full = True

    def setProject(self, project):
        self.project = project

    def setExclProj(self, proj_list):
        for proj in proj_list:
            self.excl_projs.append(proj)

    def setEndDate(self, end_date_string):
        """ Format : YYYY-MM-DD"""
        # Default : today
        if end_date_string == None :
            d =  datetime.datetime.now()
            self.end_date = datetime.datetime(
                d.year, d.month, d.day, 23, 59, 59)
        else : 
            (year, month, day) = end_date_string.split("-")
            self.end_date = datetime.datetime(int(year), 
                                              int(month), 
                                              int(day), 
                                              23, 59, 59)

    def setBeginDate(self, begin_date_string):
        """ Format : YYYY-MM-DD"""
        if begin_date_string == None :
            self.begin_date = datetime.datetime(
                1970, 1, 1, 0, 0, 0)
        else :
            (year, month, day) = begin_date_string.split("-")
            self.begin_date = datetime.datetime(int(year), 
                                                int(month), 
                                                int(day), 
                                                0, 0, 0)
 
    def setPeriod(self, period):
        """ This overrides any "from" or "to" date that may be specified
        """
        today = datetime.datetime.now()
        if period == "this-day" :
            beg = today
            end = today
        elif period == "last-day" :
            beg = today - datetime.timedelta(1)
            end = beg
        elif period == "this-week" :
            beg = today - datetime.timedelta(today.weekday())
            end = today
        elif period == "last-week" :
            beg = today - datetime.timedelta(today.weekday() + 7)
            end = beg + datetime.timedelta(6)
        elif period == "this-month" :
            beg = datetime.date(today.year, today.month, 1)
            end = today 
        elif period == "last-month" :
            end = (datetime.date(today.year, today.month, 1) -
                   datetime.timedelta(1))
            beg = datetime.date(end.year, end.month, 1)
        elif period == "this-year" :
            beg = datetime.date(today.year, 1, 1)
            end = today
        elif period == "last-year" :
            beg = datetime.date(today.year - 1, 1, 1)
            end = datetime.date(today.year - 1, 12, 31)

        # Set times
        self.begin_date=datetime.datetime(beg.year, beg.month, beg.day,
                                         0, 0, 0)
        self.end_date=datetime.datetime(end.year, end.month, end.day,
                                       23, 59, 59)
 

    def create_statistic(self, project):
        if self.printer == None:
            print("Printer is None")
            sys.exit(1)

        # Get data from taskwarrior
        try:
            if self.project!=None:
                # Only export tasks from the specified project
                json_tmp = subprocess.check_output([self.task_cmd, 
                                                    "export", 
                                                    "pro:" + self.project,
                                                    "rc.json.array=on",
                                                    ])
            else:
                # Otherwise import all
                json_tmp = subprocess.check_output([self.task_cmd, 
                                                    "export", 
                                                    "rc.json.array=on"])
        except OSError as e:
            print(str(e))
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print("Export from taskwarrior fails: " + str(e.output, encoding="utf8"))
            sys.exit(1)

        # Make valid JSON
        json_str=str(json_tmp, encoding="utf8")

        # Parse JSON
        tasks = json.loads(json_str)

        # Print data
        (counter, breakdown) = self.handle_tasks(tasks)
        total_time = 0
        self.printer.print_period(self.begin_date, self.end_date)
        for proj in sorted(counter.keys()):
            if counter[proj] == 0:
                continue
            total_time += counter[proj]
            if self.print_full :
                self.printer.print_header(proj)
                for t in breakdown[proj] :
                    self.printer.print_task(t["desc"],
                                            t["time"])
                self.printer.print_result(proj,counter[proj])
        self.printer.print_overall_results(counter, total_time)



    def handle_tasks(self, tasks):
        counter = {}
        breakdown = {}
        for t in tasks:
            tmp_seconds = self.get_task_time(t)
            proj = self.get_task_project(t)
            if proj in self.excl_projs :
                continue
            if tmp_seconds != 0 or self.print_null :
                # If this is the first task found for this project, 
                # initialize counter and breakdown structure
                if proj not in counter :
                    counter[proj] = 0
                    breakdown[proj] = []

                counter[proj] += tmp_seconds
                breakdown[proj].append({"desc":t["description"],
                                        "time":tmp_seconds})
        return (counter, breakdown)

    def get_task_project(self, task):
        if "project" in task:
            return task["project"]
        else :
            return "none"

    def get_task_time(self, task):
        seconds = 0

        last_start = ""
        if "annotations" in task:
            annotations = task["annotations"]
            for a in annotations:
                if a["description"] == "Started task":
                    last_start = a["entry"]
                elif a["description"] == "Stopped task":
                    seconds += self.calc_time_delta(last_start, a["entry"])

        return seconds

    def calc_time_delta(self, start, stop):
        start_time = self.internal_to_datetime(start)
        stop_time = self.internal_to_datetime(stop)
        # Eliminate work shifts outside of report boundaries
        if stop_time < self.begin_date or start_time > self.end_date :
            return 0
        # Trim parts outside of wanted range
        if start_time < self.begin_date :
            start_time = self.begin_date
        if stop_time > self.end_date :
            stop_time = self.end_date
        delta = stop_time - start_time
        return delta.total_seconds()

    def internal_to_datetime(self, string):
        match = re.search("^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$", 
                          string)
        if match == None:
            return None
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5))
        second = int(match.group(6))
        return datetime.datetime(year, month, day, hour, minute, second)

#
# Printer
#

class Printer:
    def print_period(self, from_date, to_date):
        raise NotImplementedError()

    def print_header(self, project):
        raise NotImplementedError()
    
    def print_task(self, description, seconds):
        raise NotImplementedError()
    
    def print_result(self, seconds):
        raise NotImplementedError()

    def print_overall_results(self, counter, total_time):
        raise NotImplementedError()

    def seconds_to_readable(self, seconds):
        second = seconds % 60
        minute = (seconds // 60) % 60
        hour = (seconds // 3600)

        return self._number_to_2_digits(hour) + ":" + self._number_to_2_digits(minute) + ":" + self._number_to_2_digits(second)

    def _number_to_2_digits(self, n):
        return repr(round(n)).zfill(2)

# CSV
class CSVPrinter(Printer):
    def _csv_encode(self, string):
        return string.replace("\"", "\"\"")

    def print_period(self, from_date, to_date):
        print(("\"Period : from {0:02d}-{1:02d}-{2:02d} " +
              " to {3:02d}-{4:02d}-{5:02d}\"").format(
            from_date.year,
            from_date.month,
            from_date.day,
            to_date.year,
            to_date.month,
            to_date.day)
        )

    def print_header(self, project):
        print("\"Project\",\"" + self._csv_encode(project) + "\"")
        print("\"\",\"\"")
        print("\"Description\",\"Duration (hours)\"")
        print("\"\",\"\"")

    def print_task(self, description, seconds):
        print("\"" + self._csv_encode(description) + "\",\"" + self.seconds_to_readable(seconds) + "\"")

    def print_result(self, seconds):
        print("\"\",\"\"")
        print("\"Sum\",\"" + self.seconds_to_readable(seconds) + "\"")

    def print_overall_results(self, counter, total_time):
        # No use for CSV
        pass



# Readable
class ReadablePrinter(Printer):
    def print_period(self, from_date, to_date):
        print(("Period : from {0:02d}-{1:02d}-{2:02d} " +
               " to {3:02d}-{4:02d}-{5:02d}").format(
                   from_date.year,
                   from_date.month,
                   from_date.day,
                   to_date.year,
                   to_date.month,
                   to_date.day))
    
    def print_header(self, project):
        print("Project: " + project)
        print()

    def print_task(self, description, seconds):
        print(description)
        if seconds != 0:
            print("\tDuration: " + self.seconds_to_readable(seconds))

    def print_result(self, project, seconds):
        print()
        print("Total time on project " + project + " : " 
              + self.seconds_to_readable(seconds))
        print("-------------------------------------------------------")

    def print_overall_results(self, counter, total_time):
        print("Project / Total time on project / percentage")
        for proj in sorted(counter.keys()) :
            if counter[proj] == 0 :
                continue
            print("{0:20s} {1:10s} {2:3d}%".format(
                proj,
                self.seconds_to_readable(counter[proj]),
                int(100*counter[proj]/total_time)))
        print("Total time : " + self.seconds_to_readable(total_time))



#
# Main
#

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        "Display total activity time for taskwarrior projects")
    parser.add_argument("-b", "--begin", dest="begin_date",
                        help = "Begin time accounting on YYYY-MM-DD," +
                        " default = 1970-01-01",
                        default=None
                       )
    parser.add_argument("-e", "--end", dest="end_date",
                        help="End time accounting on YYYY-MM-DD," +
                        " default = today",
                        default=None)
    parser.add_argument("-p", "--period", help="Period (overrides dates)",
                        choices = ["this-day",
                                   "this-week",
                                   "this-month",
                                   "this-year",
                                   "last-day",
                                   "last-week",
                                   "last-month",
                                   "last-year"])
    parser.add_argument("-c", "--csv", help="Print output in CSV format",
                        action="store_true")
    parser.add_argument("-n", "--null", 
        help="Print also tasks without time information (default: no)",
        action="store_true")
    parser.add_argument("-t", "--task",
                        help="specify task command (default : \"task\")",
                        dest="task_cmd",
                        default="task")
    parser.add_argument("-v", "--version",
                        help="Print version and exit",
                        action="version",
                        version='{version}'.format(version=__version__))
    parser.add_argument("--full", 
                        help=("print full task breakdown" +
                              " (default : only print totals)"),
                        action="store_true")
    parser.add_argument("--project", 
                        help="Project for which the active time is computed")
    parser.add_argument("-x", "--exclude", action='append',
                        help="Exclude project (may be used more than once)"
                       )
    args = parser.parse_args()

    params = sys.argv[1:]
    
        
    c = Calculator()
    if args.task_cmd != None:
        c.setTaskCmd(args.task_cmd)
    if args.csv:
        c.setPrinter(CSVPrinter())
    if args.null:
        c.setPrintNull()
    if args.full :
        c.setPrintFull()
    if args.project != None :
        c.setProject(args.project)
    if args.exclude != None :
        c.setExclProj(args.exclude)


    c.setBeginDate(args.begin_date)
    c.setEndDate(args.end_date)
    
    # explicit periods overrides to/from dates
    if args.period != None :
        c.setPeriod(args.period)


    c.create_statistic(args.project)
