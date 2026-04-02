#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

from asyncio import Queue
from weakref import ReferenceType, ref


class MultiQueue[T]:
    """Implements a multi-consumer, multi-producer queue
    Each consumer uses steam to get a queue instance to iterate over
    while each producer uses send"""

    def __init__(self):
        self.queues: list[ReferenceType[Queue[T]]] = []

    def get_queue(self) -> Queue[T]:
        result: Queue[T] = Queue()
        self.queues.append(ref(result))
        return result

    def send(self, message: T):
        queues_copy = self.queues.copy()
        self.queues.clear()
        for queue_ref in queues_copy:
            queue = queue_ref()
            if queue is not None:
                self.queues.append(queue_ref)
                queue.put_nowait(message)


LOCAL_QUEUE: MultiQueue[bytes] = MultiQueue()
