"""The scheduling of a parallel run, ``-n N --dist loadgroup``: the ``serial`` tests run last.

A test marked ``serial`` failed beside the other workers, so it runs apart from them. Every
other test is scheduled as ``loadgroup`` does. Once only the ``serial`` group is left, each
worker that asks for more work is shut down instead, and the last one still running takes the
group when every other worker has left, then runs its tests one after another.

A worker runs the last test it holds only when more work or its shutdown arrives, so waiting
for the others to go idle would wait forever; they are shut down, and they leave.

A worker is given work until it holds two tests, or no more can be given, since one held test
waits. A worker still collecting is given none; its collection brings its work. Nor does it
hold the ``serial`` group back, and a worker whose collection differs from the run's, which
xdist never registers, holds back nothing.

A worker that dies gives back only the tests it had not started. xdist reports the one it was
running as failed, and would otherwise queue that test again with every test the worker had
finished; a finished test sent to the worker that replaces it runs nothing, so that worker
never asks for more and the run never ends.
"""

from xdist.scheduler import LoadGroupScheduling
from xdist.workermanage import WorkerController

# the group the conftest gives every test marked serial
SERIAL = "serial"


class SerialLastScheduling(LoadGroupScheduling):
    """``loadgroup`` scheduling that gives the ``serial`` group to the last worker left."""

    def _assign_work_unit(self, node: WorkerController) -> None:
        if SERIAL in self.workqueue:
            self.workqueue.move_to_end(SERIAL)
        if next(iter(self.workqueue)) != SERIAL:
            super()._assign_work_unit(node)
            return
        # a worker that has not collected, or collected other tests, is never given the group
        others = [
            other
            for other in self.assigned_work
            if other is not node and other in self.registered_collections
        ]
        if not all(other.shutting_down for other in others):
            node.shutdown()
        elif not others:
            super()._assign_work_unit(node)

    def _reschedule(self, node: WorkerController) -> None:
        """Give ``node``, once it has collected, work until it holds two tests or takes no more."""
        if node not in self.registered_collections:
            return
        while True:
            held = self._pending_of(self.assigned_work[node])
            super()._reschedule(node)
            now = self._pending_of(self.assigned_work[node])
            if now == held or now >= 2 or node.shutting_down:
                return

    def remove_node(self, node: WorkerController) -> str | None:
        """Forget a worker that left, and name the test it died in, if it died in one.

        The tests it had not started go back in the queue, and the last worker left may now take
        the ``serial`` group.
        """
        workload = self.assigned_work.pop(node)
        crashed = next(
            (test for unit in workload.values() for test, done in unit.items() if not done), None
        )
        if crashed is not None:
            workload[self._split_scope(crashed)][crashed] = True
        for scope, unit in workload.items():
            if not all(unit.values()):
                self.workqueue[scope] = unit
        if self.workqueue:
            for other in list(self.assigned_work):
                self._reschedule(other)
        return crashed
