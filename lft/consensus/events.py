from dataclasses import dataclass
from typing import Sequence, Optional

from lft.consensus.epoch import Epoch
from lft.event import Event
from lft.consensus.messages.data import Data, Vote


@dataclass
class InitializeEvent(Event):
    prev_epoch: Optional['Epoch']
    epoch: 'Epoch'
    round_num: int
    candidate_data: 'Data'
    candidate_votes: Sequence['Vote']


@dataclass
class ReceiveDataEvent(Event):
    data: 'Data'


@dataclass
class ReceiveVoteEvent(Event):
    vote: 'Vote'


@dataclass
class BroadcastDataEvent(Event):
    data: 'Data'


@dataclass
class BroadcastVoteEvent(Event):
    vote: 'Vote'


@dataclass
class RoundStartEvent(Event):
    epoch: Epoch
    round_num: int


@dataclass
class RoundEndEvent(Event):
    is_success: bool
    epoch_num: int
    round_num: int
    candidate_id: Optional[bytes]
    commit_id: Optional[bytes]
