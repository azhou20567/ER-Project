import statistics

class ESI:
    def __init__(self):
        self.lengths_of_visit = {1: [], 2: [], 3: [], 4: [], 5: []}
        self.wait_times = {1: [], 2: [], 3: [], 4: [], 5: []} # creates a dictionary of lists to store wait times for each ESI level

    def record_wait_time(self, esi_level, wait_time):
        self.wait_times[esi_level].append(wait_time) # just taking wait time measured and storing in list for the patient's ESI level

    def record_length_of_visit(self, esi_level, length_of_visit):
        self.lengths_of_visit[esi_level].append(length_of_visit)

    def report(self):
        for level in self.wait_times:
            if self.wait_times[level]: # if there are wait times recorded for this ESI level
                waits = self.wait_times[level]

                count = len(waits) # counts how many patients are in this ESI level
                average_wait = sum(waits) / count # calculate average wait time
                median_wait = statistics.median(waits)

                print(
                    "ESI Level: ",
                    level,
                    "Patients: ",
                    count,
                    "Avg: ",
                    round(average_wait, 2),
                    "min",
                    "Median: ",
                    round(median_wait, 2),
                    "min",
                )

        for level, visits in self.lengths_of_visit.items():
            if visits:
                print(
                    "ESI Level: ", level,
                    "Completed visits: ", len(visits),
                    "Mean simulated LOV: ", round(statistics.mean(visits), 2), "min",
                    "Median simulated LOV: ", round(statistics.median(visits), 2), "min",
                )
