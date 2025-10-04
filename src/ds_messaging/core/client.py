"""Client helpers that handle leader failover transparently."""

from __future__ import annotations

import asyncio
from typing import Iterable, List, Optional

import aiohttp


class FailoverMessagingClient:
	"""Small aiohttp-based helper that follows leader changes automatically.

	The client maintains a list of seed nodes and will fall back to alternative
	nodes if the current leader becomes unavailable.  On redirects (307) it
	updates the active leader using the ``leader_url`` field returned by the
	server.  When all requests fail, :class:`RuntimeError` is raised.
	"""

	def __init__(
		self,
		seeds: Iterable[str],
		*,
		request_timeout: float = 5.0,
		session: Optional[aiohttp.ClientSession] = None,
	) -> None:
		self._seeds: List[str] = list(seeds)
		if not self._seeds:
			raise ValueError("At least one seed endpoint must be provided")
		self._timeout = aiohttp.ClientTimeout(total=request_timeout)
		self._session = session
		self._owned_session = session is None
		self._leader_url: Optional[str] = None
		self._seed_index = 0
		self._lock = asyncio.Lock()

	async def __aenter__(self) -> "FailoverMessagingClient":
		if self._session is None:
			self._session = aiohttp.ClientSession(timeout=self._timeout)
		return self

	async def __aexit__(self, exc_type, exc, tb) -> None:
		if self._owned_session and self._session:
			await self._session.close()
		self._session = None
		self._leader_url = None

	async def send(self, payload: dict) -> dict:
		"""Send a message via ``/send`` with automatic leader failover."""

		return await self.request("POST", "/send", json=payload)

	async def request(self, method: str, path: str, *, json: Optional[dict] = None) -> dict:
		"""Perform an HTTP request with retry semantics.

		The client retries once per known seed.  After every failure the local
		leader cache is invalidated so the next attempt triggers a fresh status
		probe.
		"""

		last_error: Optional[Exception] = None
		for _ in range(len(self._seeds)):
			base_url = await self._get_active_leader()
			if base_url is None:
				continue
			try:
				assert self._session is not None
				async with self._session.request(method, f"{base_url}{path}", json=json) as resp:
					if resp.status in (200, 201):
						return await resp.json()
					if resp.status == 307:
						data = await resp.json()
						new_leader = data.get("leader_url")
						if new_leader:
							self._leader_url = new_leader
							continue
					raise RuntimeError(f"Request failed with status {resp.status}")
			except Exception as exc:  # pragma: no cover - network failures
				last_error = exc
				self._leader_url = None
		if last_error is not None:
			raise RuntimeError("All leader candidates failed") from last_error
		raise RuntimeError("Unable to determine cluster leader")

	async def _get_active_leader(self) -> Optional[str]:
		async with self._lock:
			if self._leader_url:
				return self._leader_url

			session = self._session
			if session is None:
				session = aiohttp.ClientSession(timeout=self._timeout)
				self._session = session
				self._owned_session = True

			for _ in range(len(self._seeds)):
				seed = self._seeds[self._seed_index]
				self._seed_index = (self._seed_index + 1) % len(self._seeds)
				try:
					async with session.get(f"{seed}/status") as resp:
						if resp.status != 200:
							continue
						data = await resp.json()
						consensus = data.get("consensus", {})
						if consensus.get("role") == "Leader":
							self._leader_url = seed
							return seed
						leader_url = consensus.get("leader_url")
						if leader_url:
							self._leader_url = leader_url
							return leader_url
				except Exception:  # pragma: no cover - network failures
					continue

			return None


__all__ = ["FailoverMessagingClient"]
