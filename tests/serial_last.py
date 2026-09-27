"""The scheduling of a parallel run, ``-n N --dist loadgroup``: the ``serial`` tests run last.

A test marked ``serial`` measures time against the machine's load, so it runs by itself. Every
other test is scheduled as ``loadgroup`` does. Once only the ``serial`` group is left, each
worker that asks for more work is shut down instead, and the last one still running takes the
group when every other worker has left, then runs its tests one after another.

A worker runs the last test it holds only when more work or its shutdown arrives, so waiting
for the others to go idle would wait forever; they are shut down, and they leave.
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
        others = [other for other in self.assigned_work if other is not node]
        if not all(other.shutting_down for other in others):
            node.shutdown()
        elif not others:
            super()._assign_work_unit(node)

    def remove_node(self, node: WorkerController) -> str | None:
        """Forget a worker that left; the last one left may now take the ``serial`` group."""
        crashed = super().remove_node(node)
        if SERIAL in self.workqueue:
            for other in list(self.assigned_work):
                self._reschedule(other)
        return crashed
