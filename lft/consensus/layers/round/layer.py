import logging
from typing import Sequence

from lft.consensus.candidate import Candidate
from lft.consensus.layers.round import RoundMessages
from lft.consensus.messages.data import Data, DataVerifier, DataFactory
from lft.consensus.messages.vote import Vote, VoteVerifier, VoteFactory
from lft.consensus.events import (RoundEndEvent, BroadcastDataEvent, BroadcastVoteEvent,
                                  ReceiveDataEvent, ReceiveVoteEvent, ChangedCandidateEvent)
from lft.consensus.term import Term
from lft.consensus.exceptions import InvalidProposer, AlreadyCompleted, AlreadyVoted, CannotComplete
from lft.event import EventSystem


class RoundLayer:
    def __init__(self, node_id: bytes, event_system: EventSystem, data_factory: DataFactory,
                 vote_factory: VoteFactory):
        self._event_system: EventSystem = event_system
        self._data_factory: DataFactory = data_factory
        self._vote_factory: VoteFactory = vote_factory
        self._logger = logging.getLogger(node_id.hex())

        self._data_verifier: DataVerifier = None
        self._vote_verifier: VoteVerifier = None

        self._candidate: Candidate = None
        self._messages: RoundMessages = None

        self._term: Term = None
        self._round_num = -1

        self._node_id: bytes = node_id
        self._is_voted = False

    async def initialize(self, term: Term, round_num: int, candidate_data: Data, votes: Sequence[Vote]):
        self._data_verifier = await self._data_factory.create_data_verifier()
        self._vote_verifier = await self._vote_factory.create_vote_verifier()

        self._candidate = Candidate(
            data=candidate_data,
            votes=votes
        )
        await self._start_new_round(
            term=term,
            round_num=round_num
        )

    async def round_start(self, term: Term, round_num: int):
        await self._start_new_round(
            term=term,
            round_num=round_num
        )
        self._is_voted = False

    async def propose_data(self, data: Data):
        try:
            self._messages.add_data(data)
        except AlreadyCompleted:
            pass
        else:
            if not self._is_voted:
                await self._verify_and_broadcast_vote(data)
                self._is_voted = True

            await self._update_round_if_complete()

    async def vote_data(self, vote: Vote):
        try:
            self._messages.add_vote(vote)
        except AlreadyCompleted:
            pass
        except AlreadyVoted:
            pass
        else:
            await self._update_round_if_complete()

    async def change_candidate(self, candidate: Candidate):
        if candidate.data.term_num == self._term.num and candidate.data.round_num > self._round_num:
            self._candidate = candidate
            self._event_system.simulator.raise_event(
                ChangedCandidateEvent(
                    candidate.data, candidate.votes
                )
            )
            await self._start_new_round(self._term, candidate.data.round_num)
        elif not self._messages.is_completed:
            self._candidate = candidate
            self._event_system.simulator.raise_event(
                ChangedCandidateEvent(
                    candidate.data, candidate.votes
                )
            )

    async def _update_round_if_complete(self):
        try:
            self._messages.complete()
        except AlreadyCompleted:
            pass
        except CannotComplete:
            pass
        else:
            candidate = self._messages.result()
            await self._raise_round_end(candidate)
            if candidate.data:
                self._candidate = candidate

    async def _raise_broadcast_data(self, data):
        self._event_system.simulator.raise_event(
            BroadcastDataEvent(
                data=data
            )
        )
        self._event_system.simulator.raise_event(
            ReceiveDataEvent(
                data=data
            )
        )

    async def _raise_broadcast_vote(self, vote: Vote):
        self._event_system.simulator.raise_event(
            BroadcastVoteEvent(
                vote=vote)
        )
        self._event_system.simulator.raise_event(
            ReceiveVoteEvent(
                vote=vote
            )
        )

    async def _raise_round_end(self, candidate: Candidate):
        if candidate.data:
            round_end = RoundEndEvent(
                is_success=True,
                term_num=self._term.num,
                round_num=self._round_num,
                candidate_votes=candidate.votes,
                candidate_data=candidate.data,
                commit_id=candidate.data.prev_id
            )
        else:
            round_end = RoundEndEvent(
                is_success=False,
                term_num=self._term.num,
                round_num=self._round_num,
                candidate_votes=candidate.votes,
                candidate_data=None,
                commit_id=None
            )
        self._event_system.simulator.raise_event(round_end)

    async def _start_new_round(self, term: Term, round_num: int):
        self._term = term
        self._round_num = round_num
        self._messages = RoundMessages(self._term)

        none_data = await self._data_factory.create_none_data(term_num=term.num,
                                                              round_num=round_num,
                                                              proposer_id=term.get_proposer_id(round_num))
        self._messages.add_data(none_data)

        await self._create_data_if_proposer()

    async def _create_data_if_proposer(self):
        try:
            self._term.verify_proposer(self._node_id, self._round_num)
        except InvalidProposer:
            pass
        else:
            new_data = await self._data_factory.create_data(
                data_number=self._candidate.data.number + 1,
                prev_id=self._candidate.data.id,
                term_num=self._term.num,
                round_num=self._round_num,
                prev_votes=self._candidate.votes
            )
            await self._raise_broadcast_data(new_data)

    async def _verify_and_broadcast_vote(self, data):
        if await self._verify_data(data):
            vote = await self._vote_factory.create_vote(data_id=data.id,
                                                        commit_id=self._candidate.data.id,
                                                        term_num=self._term.num,
                                                        round_num=self._round_num)
        else:
            vote = await self._vote_factory.create_none_vote(term_num=self._term.num,
                                                             round_num=self._round_num)
        await self._raise_broadcast_vote(vote)

    async def _verify_data(self, data):
        if data.proposer_id == self._node_id:
            return True
        if self._candidate.data.id != data.prev_id:
            return False
        if data.is_not():
            return False
        try:
            await self._data_verifier.verify(data)
        except Exception as e:
            return False
        else:
            return True
