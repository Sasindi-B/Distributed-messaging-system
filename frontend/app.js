const { useState, useEffect, useCallback } = React;

const formatDate = (epochSeconds) => {
  if (!epochSeconds) {
    return "-";
  }
  try {
    return new Date(epochSeconds * 1000).toLocaleString();
  } catch (err) {
    return String(epochSeconds);
  }
};

const normalizeBaseUrl = (raw) => raw.trim().replace(/\/$/, "");

const valueOrFallback = (value, fallbackValue) => {
  if (value === undefined || value === null || value === "") {
    return fallbackValue;
  }
  return value;
};

const formatNumber = (value, { defaultValue = "-", digits = 3 } = {}) => {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return defaultValue;
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return defaultValue;
  }
  if (Math.abs(numeric) >= 1000) {
    return numeric.toLocaleString();
  }
  return numeric.toFixed(digits);
};

const getConsensus = (status) => {
  if (!status || typeof status !== "object") {
    return {};
  }
  const consensus = status.consensus;
  if (!consensus || typeof consensus !== "object") {
    return {};
  }
  return consensus;
};

const getPeerEntries = (status) => {
  if (!status || typeof status !== "object") {
    return [];
  }
  const peerStatus = status.peer_status;
  if (!peerStatus || typeof peerStatus !== "object") {
    return [];
  }
  return Object.entries(peerStatus);
};

function App() {
  const [baseUrl, setBaseUrl] = useState("http://127.0.0.1:8000");
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messagesError, setMessagesError] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [polling, setPolling] = useState(true);
  const [form, setForm] = useState({ sender: "", recipient: "", payload: "", msg_id: "" });
  const [sendState, setSendState] = useState({ loading: false, error: null, success: null });
  const [messageFilters, setMessageFilters] = useState({ limit: "50", after: "", sender: "", recipient: "" });
  const [timeSyncState, setTimeSyncState] = useState({ loading: false, success: null, error: null, details: null });
  const [timeCorrectionForm, setTimeCorrectionForm] = useState({ timestamp: "", sender: "" });
  const [timeCorrectionState, setTimeCorrectionState] = useState({ loading: false, result: null, error: null });
  const [orderingState, setOrderingState] = useState({ loading: false, data: null, error: null });
  const [forceDeliveryState, setForceDeliveryState] = useState({ loading: false, result: null, error: null });

  const fetchStatus = useCallback(async (showSpinner = true) => {
    const url = normalizeBaseUrl(baseUrl);
    if (!url) {
      setStatus(null);
      return;
    }
    try {
      if (showSpinner) {
        setLoadingStatus(true);
      }
      const response = await fetch(url + "/status");
      if (!response.ok) {
        throw new Error("Status request failed (" + response.status + ")");
      }
      const data = await response.json();
      setStatus(data);
      setStatusError(null);
    } catch (err) {
      setStatus(null);
      setStatusError(err && err.message ? err.message : String(err));
    } finally {
      if (showSpinner) {
        setLoadingStatus(false);
      }
    }
  }, [baseUrl]);

  const fetchMessages = useCallback(async (showSpinner = true) => {
    const url = normalizeBaseUrl(baseUrl);
    if (!url) {
      setMessages([]);
      return;
    }
    try {
      if (showSpinner) {
        setLoadingMessages(true);
      }
      const params = new URLSearchParams();
      const limitVal = parseInt(messageFilters.limit, 10);
      params.set("limit", Number.isFinite(limitVal) && limitVal > 0 ? String(limitVal) : "50");
      if (messageFilters.after.trim()) {
        params.set("after", messageFilters.after.trim());
      }
      if (messageFilters.sender.trim()) {
        params.set("sender", messageFilters.sender.trim());
      }
      if (messageFilters.recipient.trim()) {
        params.set("recipient", messageFilters.recipient.trim());
      }
      const response = await fetch(`${url}/messages?${params.toString()}`);
      if (!response.ok) {
        throw new Error("Messages request failed (" + response.status + ")");
      }
      const data = await response.json();
      const nextMessages = Array.isArray(data.messages) ? data.messages : [];
      setMessages(nextMessages);
      setMessagesError(null);
    } catch (err) {
      setMessages([]);
      setMessagesError(err && err.message ? err.message : String(err));
    } finally {
      if (showSpinner) {
        setLoadingMessages(false);
      }
    }
  }, [baseUrl, messageFilters]);

  useEffect(() => {
    fetchStatus();
    fetchMessages();
  }, [fetchStatus, fetchMessages]);

  useEffect(() => {
    if (!polling) {
      return undefined;
    }
    const interval = setInterval(() => {
      fetchStatus(false);
      fetchMessages(false);
    }, 3500);
    return () => clearInterval(interval);
  }, [polling, fetchStatus, fetchMessages]);

  useEffect(() => {
    setTimeCorrectionForm((prev) => {
      if (prev.timestamp && prev.timestamp.trim() !== "") {
        return prev;
      }
      return { ...prev, timestamp: String(Math.round(Date.now() / 1000)) };
    });
  }, []);

  const handleMessageFilterChange = (field) => (event) => {
    const value = event.target.value;
    setMessageFilters((prev) => ({ ...prev, [field]: value }));
  };

  const resetMessageFilters = () => {
    setMessageFilters({ limit: "50", after: "", sender: "", recipient: "" });
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const url = normalizeBaseUrl(baseUrl);
    if (!url) {
      setSendState({ loading: false, error: "Set a base URL before sending", success: null });
      return;
    }
    if (!form.payload.trim()) {
      setSendState({ loading: false, error: "Message payload cannot be empty", success: null });
      return;
    }

    const body = {
      payload: form.payload,
      sender: form.sender.trim() || undefined,
      recipient: form.recipient.trim() || undefined,
    };
    if (form.msg_id.trim()) {
      body.msg_id = form.msg_id.trim();
    }

    const requestPayload = JSON.stringify(body);

    const sendWithLeaderRedirect = async (targetUrl, allowRedirect) => {
      const response = await fetch(targetUrl + "/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: requestPayload,
      });

      if (response.status === 307) {
        let redirectData = {};
        try {
          redirectData = await response.json();
        } catch (_) {
          redirectData = {};
        }
        const leaderUrl = typeof redirectData.leader_url === "string" ? redirectData.leader_url : null;
        if (leaderUrl && allowRedirect) {
          setBaseUrl((prev) => {
            const normalized = normalizeBaseUrl(leaderUrl);
            return normalized || prev;
          });
          return sendWithLeaderRedirect(normalizeBaseUrl(leaderUrl), false);
        }
        const reason = redirectData.reason || "node_is_not_leader";
        throw new Error("Redirected to leader required: " + reason);
      }

      if (!response.ok) {
        let errorDetail = "";
        try {
          const errorJson = await response.json();
          if (errorJson && errorJson.reason) {
            errorDetail = ": " + errorJson.reason;
          }
        } catch (_) {
          try {
            const text = await response.text();
            if (text) {
              errorDetail = ": " + text;
            }
          } catch (_) {
            errorDetail = "";
          }
        }
        throw new Error("Send request failed (" + response.status + ")" + errorDetail);
      }

      return response.json();
    };

    setSendState({ loading: true, error: null, success: null });
    try {
      const result = await sendWithLeaderRedirect(url, true);
      setSendState({ loading: false, error: null, success: "Message accepted by node" });
      setForm({ sender: "", recipient: "", payload: "", msg_id: "" });
      if (result && result.leader_url && normalizeBaseUrl(result.leader_url) !== normalizeBaseUrl(baseUrl)) {
        setBaseUrl(normalizeBaseUrl(result.leader_url));
      }
      fetchMessages(false);
    } catch (err) {
      setSendState({
        loading: false,
        error: err && err.message ? err.message : String(err),
        success: null,
      });
    }
  };

  const handleBaseUrlChange = (event) => {
    setBaseUrl(event.target.value);
  };
  const triggerTimeSync = async () => {
    const url = normalizeBaseUrl(baseUrl);
    if (!url) {
      setTimeSyncState({ loading: false, success: null, error: "Set a base URL", details: null });
      return;
    }
    setTimeSyncState({ loading: true, success: null, error: null, details: null });
    try {
      const response = await fetch(url + "/time/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result && result.message ? result.message : "Time sync failed");
      }
      setTimeSyncState({
        loading: false,
        success: result.message || "Time synchronization completed",
        error: null,
        details: result.sync_status || null,
      });
      fetchStatus(false);
    } catch (err) {
      setTimeSyncState({
        loading: false,
        success: null,
        error: err && err.message ? err.message : String(err),
        details: null,
      });
    }
  };

  const handleTimeCorrectionSubmit = async (event) => {
    event.preventDefault();
    const url = normalizeBaseUrl(baseUrl);
    if (!url) {
      setTimeCorrectionState({ loading: false, result: null, error: "Set a base URL" });
      return;
    }
    const timestampValue = timeCorrectionForm.timestamp.trim();
    if (!timestampValue) {
      setTimeCorrectionState({ loading: false, result: null, error: "Enter a timestamp" });
      return;
    }
    let numericTimestamp = Number(timestampValue);
    if (!Number.isFinite(numericTimestamp)) {
      setTimeCorrectionState({ loading: false, result: null, error: "Timestamp must be numeric" });
      return;
    }
    setTimeCorrectionState({ loading: true, result: null, error: null });
    try {
      const payload = {
        timestamp: numericTimestamp,
      };
      if (timeCorrectionForm.sender.trim()) {
        payload.sender = timeCorrectionForm.sender.trim();
      }
      const response = await fetch(url + "/time/correct", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result && result.message ? result.message : "Correction failed");
      }
      setTimeCorrectionState({ loading: false, result, error: null });
    } catch (err) {
      setTimeCorrectionState({
        loading: false,
        result: null,
        error: err && err.message ? err.message : String(err),
      });
    }
  };

  const fetchOrderingStatus = async () => {
    const url = normalizeBaseUrl(baseUrl);
    if (!url) {
      setOrderingState({ loading: false, data: null, error: "Set a base URL" });
      return;
    }
    setOrderingState({ loading: true, data: null, error: null });
    try {
      const response = await fetch(url + "/ordering/status");
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data && data.message ? data.message : "Failed to fetch ordering status");
      }
      setOrderingState({ loading: false, data, error: null });
    } catch (err) {
      setOrderingState({
        loading: false,
        data: null,
        error: err && err.message ? err.message : String(err),
      });
    }
  };

  const forceDelivery = async () => {
    const url = normalizeBaseUrl(baseUrl);
    if (!url) {
      setForceDeliveryState({ loading: false, result: null, error: "Set a base URL" });
      return;
    }
    setForceDeliveryState({ loading: true, result: null, error: null });
    try {
      const response = await fetch(url + "/ordering/force_delivery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result && result.message ? result.message : "Force delivery failed");
      }
      setForceDeliveryState({ loading: false, result, error: null });
      fetchMessages(false);
    } catch (err) {
      setForceDeliveryState({
        loading: false,
        result: null,
        error: err && err.message ? err.message : String(err),
      });
    }
  };

  const togglePolling = () => {
    setPolling((prev) => !prev);
  };

  const consensus = getConsensus(status);
  const peerEntries = getPeerEntries(status);
  const nodeIdLabel = valueOrFallback(status && status.node_id, "-");
  const portLabel = valueOrFallback(status && status.port, "-");
  const replicationModeLabel = valueOrFallback(status && status.replication_mode, "-");
  const quorumLabel = valueOrFallback(status && status.quorum, "-");
  const consensusRoleLabel = valueOrFallback(consensus.role, "-");
  const consensusTermLabel = valueOrFallback(consensus.current_term, "-");
  const leaderIdLabel = valueOrFallback(consensus.leader_id, "Unknown");
  const leaderUrlLabel = valueOrFallback(consensus.leader_url, "Unknown");
  const committedSeqLabel = valueOrFallback(status && status.committed_seq, "-");
  const commitIndexLabel = valueOrFallback(status && status.commit_index, "-");
  const metrics = status && status.metrics ? status.metrics : {};
  const timeSync = status && status.time_sync ? status.time_sync : {};
  const recentDeliveries = Array.isArray(status && status.recent_deliveries)
    ? status.recent_deliveries
    : [];

  return (
    <main className="layout">
      <header className="page-header">
        <h1>Messaging Cluster Dashboard</h1>
        <p>Monitor node health, inspect replicated logs, and inject test traffic.</p>
      </header>

      <section className="card">
        <h2>Cluster Connection</h2>
        <div className="connection-controls">
          <label htmlFor="baseUrl">Base API URL</label>
          <input
            id="baseUrl"
            type="text"
            value={baseUrl}
            onChange={handleBaseUrlChange}
            placeholder="http://127.0.0.1:8000"
            spellCheck={false}
          />
          <button type="button" onClick={() => fetchStatus()} disabled={loadingStatus}>
            Refresh Status
          </button>
          <button type="button" onClick={() => fetchMessages()} disabled={loadingMessages}>
            Refresh Messages
          </button>
          <button type="button" onClick={togglePolling}>
            {polling ? "Pause Auto-Refresh" : "Resume Auto-Refresh"}
          </button>
        </div>
        {statusError ? <p className="error">{statusError}</p> : null}
        {messagesError ? <p className="error">{messagesError}</p> : null}
        {(loadingStatus || loadingMessages) && !statusError && !messagesError ? (
          <p style={{ marginTop: "0.5rem" }}>Loading data from the node.</p>
        ) : null}
      </section>

      <section className="card">
        <h2>Node Overview</h2>
        {status ? (
          <>
            <div className="status-grid">
              <div className="status-item">
                <span>Node ID</span>
                <strong>{nodeIdLabel}</strong>
              </div>
              <div className="status-item">
                <span>Host</span>
                <strong>{valueOrFallback(status && status.host, "-")}</strong>
              </div>
              <div className="status-item">
                <span>Port</span>
                <strong>{portLabel}</strong>
              </div>
              <div className="status-item">
                <span>Replication Mode</span>
                <strong>{replicationModeLabel}</strong>
              </div>
              <div className="status-item">
                <span>Quorum</span>
                <strong>{quorumLabel}</strong>
              </div>
              <div className="status-item">
                <span>Role</span>
                <strong>{consensusRoleLabel}</strong>
              </div>
              <div className="status-item">
                <span>Current Term</span>
                <strong>{consensusTermLabel}</strong>
              </div>
              <div className="status-item">
                <span>Leader</span>
                <strong>{leaderIdLabel}</strong>
              </div>
              <div className="status-item">
                <span>Leader URL</span>
                <strong>{leaderUrlLabel}</strong>
              </div>
              <div className="status-item">
                <span>Committed Sequence</span>
                <strong>{committedSeqLabel}</strong>
              </div>
              <div className="status-item">
                <span>Commit Index</span>
                <strong>{commitIndexLabel}</strong>
              </div>
            </div>

            <h3 style={{ marginTop: "1.5rem" }}>Peer Health</h3>
            {peerEntries.length === 0 ? (
              <p>No peers configured for this node.</p>
            ) : (
              <div className="messages">
                {peerEntries.map(([peerUrl, health]) => (
                  <div key={peerUrl} className="message">
                    <div className="message-header">
                      <strong>{peerUrl}</strong>
                      <span>{health && health.alive ? "alive" : "unreachable"}</span>
                    </div>
                    <div className="message-payload">
                      Last OK: {formatDate(health && health.last_ok)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : !loadingStatus && !statusError ? (
          <p>Select a node and refresh to see status.</p>
        ) : null}
      </section>

      <section className="card">
        <h2>Delivery Metrics &amp; Time Sync</h2>
        {status ? (
          <>
            <div className="status-grid">
              <div className="status-item">
                <span>Avg Store Latency (s)</span>
                <strong>{formatNumber(metrics.average_store_latency)}</strong>
              </div>
              <div className="status-item">
                <span>Avg Correction (s)</span>
                <strong>{formatNumber(metrics.average_correction_magnitude)}</strong>
              </div>
              <div className="status-item">
                <span>Last Recovery</span>
                <strong>{formatDate(metrics.last_recovery_time)}</strong>
              </div>
              <div className="status-item">
                <span>Time Sync</span>
                <strong>{timeSync.synchronized ? "Synchronized" : "Not synced"}</strong>
              </div>
              <div className="status-item">
                <span>Clock Offset (s)</span>
                <strong>{formatNumber(timeSync.clock_offset)}</strong>
              </div>
              <div className="status-item">
                <span>Sync Accuracy (s)</span>
                <strong>{formatNumber(timeSync.sync_accuracy)}</strong>
              </div>
              <div className="status-item">
                <span>Drift Rate (s/s)</span>
                <strong>{formatNumber(timeSync.drift_rate, { digits: 6 })}</strong>
              </div>
              <div className="status-item">
                <span>Last Sync</span>
                <strong>{formatDate(timeSync.last_sync_time)}</strong>
              </div>
            </div>

            <h3 style={{ marginTop: "1.5rem" }}>Peer Offsets</h3>
            {timeSync.peer_offsets && Object.keys(timeSync.peer_offsets).length > 0 ? (
              <div className="messages metrics-list">
                {Object.entries(timeSync.peer_offsets).map(([peer, offset]) => (
                  <div key={peer} className="message">
                    <div className="message-header">
                      <strong>{peer}</strong>
                      <span>{formatNumber(offset)}</span>
                    </div>
                    <div className="message-payload">
                      Delay: {formatNumber(timeSync.peer_delays && timeSync.peer_delays[peer])} s
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p>No peer offset data available yet.</p>
            )}
          </>
        ) : (
          <p>Select a node to view metrics.</p>
        )}
      </section>

      <section className="card">
        <h2>Send a Message</h2>
        <form onSubmit={handleSubmit}>
          <div className="field-group">
            <label htmlFor="sender">Sender (optional)</label>
            <input
              id="sender"
              type="text"
              value={form.sender}
              onChange={(event) => setForm((prev) => ({ ...prev, sender: event.target.value }))}
              placeholder="producer-A"
            />
          </div>
          <div className="field-group">
            <label htmlFor="recipient">Recipient (optional)</label>
            <input
              id="recipient"
              type="text"
              value={form.recipient}
              onChange={(event) => setForm((prev) => ({ ...prev, recipient: event.target.value }))}
              placeholder="broadcast"
            />
          </div>
          <div className="field-group">
            <label htmlFor="payload">Payload</label>
            <textarea
              id="payload"
              value={form.payload}
              onChange={(event) => setForm((prev) => ({ ...prev, payload: event.target.value }))}
              placeholder="Type the message body"
            />
          </div>
          <div className="field-group">
            <label htmlFor="msg_id">Message ID (optional)</label>
            <input
              id="msg_id"
              type="text"
              value={form.msg_id}
              onChange={(event) => setForm((prev) => ({ ...prev, msg_id: event.target.value }))}
              placeholder="auto-generated if left blank"
            />
          </div>
          <div>
            <button type="submit" disabled={sendState.loading}>
              {sendState.loading ? "Sending..." : "Send Message"}
            </button>
          </div>
          {sendState.error ? <p className="error">{sendState.error}</p> : null}
          {sendState.success ? (
            <p style={{ color: "#047857", marginTop: "0.25rem" }}>{sendState.success}</p>
          ) : null}
        </form>
      </section>

      <section className="card">
        <h2>Replicated Messages</h2>
        <div className="filter-grid">
          <div className="field-group">
            <label htmlFor="filterLimit">Limit</label>
            <input
              id="filterLimit"
              type="number"
              min="1"
              value={messageFilters.limit}
              onChange={handleMessageFilterChange("limit")}
            />
          </div>
          <div className="field-group">
            <label htmlFor="filterAfter">After Seq</label>
            <input
              id="filterAfter"
              type="text"
              value={messageFilters.after}
              onChange={handleMessageFilterChange("after")}
              placeholder="e.g. 42"
            />
          </div>
          <div className="field-group">
            <label htmlFor="filterSender">Sender</label>
            <input
              id="filterSender"
              type="text"
              value={messageFilters.sender}
              onChange={handleMessageFilterChange("sender")}
              placeholder="filter by sender"
            />
          </div>
          <div className="field-group">
            <label htmlFor="filterRecipient">Recipient</label>
            <input
              id="filterRecipient"
              type="text"
              value={messageFilters.recipient}
              onChange={handleMessageFilterChange("recipient")}
              placeholder="filter by recipient"
            />
          </div>
          <div className="filter-actions">
            <button type="button" onClick={() => fetchMessages()} disabled={loadingMessages}>
              Apply Filters
            </button>
            <button type="button" onClick={resetMessageFilters} disabled={loadingMessages}>
              Reset
            </button>
          </div>
        </div>
        {loadingMessages ? <p>Loading messages...</p> : null}
        {messagesError ? <p className="error">{messagesError}</p> : null}
        {!loadingMessages && !messagesError ? (
          messages.length === 0 ? (
            <div className="empty-state">No messages yet. Send one above to get started.</div>
          ) : (
            <div className="messages">
              {messages.map((msg) => {
                const messageKey =
                  msg && msg.msg_id !== undefined && msg.msg_id !== null && msg.msg_id !== ""
                    ? msg.msg_id
                    : msg && msg.seq;
                const senderLabel = valueOrFallback(msg && msg.sender, "unknown");
                const recipientLabel = valueOrFallback(msg && msg.recipient, "all");
                return (
                    <div className="message" key={messageKey}>
                    <div className="message-header">
                      <span>Seq #{msg && msg.seq} - {formatDate(msg && msg.ts)}</span>
                      <span>{senderLabel} &rarr; {recipientLabel}</span>
                    </div>
                    <div className="message-payload">{valueOrFallback(msg && msg.payload, "")}</div>
                    {msg && msg.msg_id ? (
                      <div className="message-header" style={{ marginTop: "0.4rem" }}>
                        <span>Message ID</span>
                        <span>{msg.msg_id}</span>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )
        ) : null}
      </section>

      {status ? (
        <section className="card">
          <h2>Recent Deliveries</h2>
          {recentDeliveries.length === 0 ? (
            <p>No recent deliveries recorded.</p>
          ) : (
            <div className="messages">
              {recentDeliveries.map((delivery, index) => {
                const key =
                  delivery.msg_id ||
                  (delivery.corrected_timestamp ? `delivery-${delivery.corrected_timestamp}` : `delivery-${index}`);
                return (
                  <div key={key} className="message">
                    <div className="message-header">
                      <span>{delivery.msg_id || "(no id)"}</span>
                      <span>{delivery.sender || "unknown"}</span>
                    </div>
                    <div className="message-payload">
                      Corrected: {formatDate(delivery.corrected_timestamp)}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      ) : null}

      <section className="card">
        <h2>Time &amp; Ordering Controls</h2>
        <div className="controls-grid">
          <div className="control-block">
            <h3>Manual Time Sync</h3>
            <p>Request an immediate synchronization round with alive peers.</p>
            <button type="button" onClick={triggerTimeSync} disabled={timeSyncState.loading}>
              {timeSyncState.loading ? "Synchronizing..." : "Trigger Time Sync"}
            </button>
            {timeSyncState.error ? <p className="error">{timeSyncState.error}</p> : null}
            {timeSyncState.success ? (
              <div className="success-box">
                <p>{timeSyncState.success}</p>
                {timeSyncState.details ? (
                  <dl className="definition-list">
                    <div>
                      <dt>Offset</dt>
                      <dd>{formatNumber(timeSyncState.details.clock_offset)}</dd>
                    </div>
                    <div>
                      <dt>Accuracy</dt>
                      <dd>{formatNumber(timeSyncState.details.sync_accuracy)}</dd>
                    </div>
                    <div>
                      <dt>Success Rate</dt>
                      <dd>{formatNumber(timeSyncState.details.success_rate, { digits: 2 })}</dd>
                    </div>
                    <div>
                      <dt>Attempts</dt>
                      <dd>{valueOrFallback(timeSyncState.details.sync_attempts, "-")}</dd>
                    </div>
                  </dl>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="control-block">
            <h3>Timestamp Correction</h3>
            <p>Submit a timestamp to get corrected value and accuracy bounds.</p>
            <form onSubmit={handleTimeCorrectionSubmit} className="inline-form">
              <div className="field-group">
                <label htmlFor="correctionTimestamp">Timestamp (seconds)</label>
                <input
                  id="correctionTimestamp"
                  type="text"
                  value={timeCorrectionForm.timestamp}
                  placeholder={String(Math.round(Date.now() / 1000))}
                  onChange={(event) =>
                    setTimeCorrectionForm((prev) => ({ ...prev, timestamp: event.target.value }))
                  }
                />
              </div>
              <div className="field-group">
                <label htmlFor="correctionSender">Sender (optional)</label>
                <input
                  id="correctionSender"
                  type="text"
                  value={timeCorrectionForm.sender}
                  onChange={(event) =>
                    setTimeCorrectionForm((prev) => ({ ...prev, sender: event.target.value }))
                  }
                />
              </div>
              <button type="submit" disabled={timeCorrectionState.loading}>
                {timeCorrectionState.loading ? "Correcting..." : "Correct Timestamp"}
              </button>
            </form>
            {timeCorrectionState.error ? <p className="error">{timeCorrectionState.error}</p> : null}
            {timeCorrectionState.result ? (
              <div className="success-box">
                <dl className="definition-list">
                  <div>
                    <dt>Original</dt>
                    <dd>{formatNumber(timeCorrectionState.result.original_timestamp)}</dd>
                  </div>
                  <div>
                    <dt>Corrected</dt>
                    <dd>{formatNumber(timeCorrectionState.result.corrected_timestamp)}</dd>
                  </div>
                  <div>
                    <dt>Accuracy</dt>
                    <dd>
                      {timeCorrectionState.result.estimated_accuracy &&
                      typeof timeCorrectionState.result.estimated_accuracy === "object"
                        ? JSON.stringify(timeCorrectionState.result.estimated_accuracy)
                        : formatNumber(timeCorrectionState.result.estimated_accuracy)}
                    </dd>
                  </div>
                </dl>
              </div>
            ) : null}
          </div>

          <div className="control-block">
            <h3>Ordering Buffer</h3>
            <p>Inspect and manage the ordering buffer for out-of-order arrivals.</p>
            <div className="button-row">
              <button type="button" onClick={fetchOrderingStatus} disabled={orderingState.loading}>
                {orderingState.loading ? "Loading..." : "Fetch Status"}
              </button>
              <button type="button" onClick={forceDelivery} disabled={forceDeliveryState.loading}>
                {forceDeliveryState.loading ? "Forcing..." : "Force Delivery"}
              </button>
            </div>
            {orderingState.error ? <p className="error">{orderingState.error}</p> : null}
            {orderingState.data ? (
              <div className="status-grid narrow">
                <div className="status-item">
                  <span>Buffer Size</span>
                  <strong>
                    {valueOrFallback(
                      orderingState.data.ordering_status
                        ? orderingState.data.ordering_status.buffer_size
                        : null,
                      "-"
                    )}
                  </strong>
                </div>
                <div className="status-item">
                  <span>Utilization</span>
                  <strong>
                    {formatNumber(
                      orderingState.data.ordering_status
                        ? orderingState.data.ordering_status.buffer_utilization
                        : null
                    )}
                  </strong>
                </div>
                <div className="status-item">
                  <span>Reordered</span>
                  <strong>
                    {valueOrFallback(
                      orderingState.data.ordering_status
                        ? orderingState.data.ordering_status.messages_reordered
                        : null,
                      "-"
                    )}
                  </strong>
                </div>
                <div className="status-item">
                  <span>Deliverable</span>
                  <strong>
                    {valueOrFallback(
                      orderingState.data.ordering_status
                        ? orderingState.data.ordering_status.deliverable_messages_count
                        : null,
                      "-"
                    )}
                  </strong>
                </div>
              </div>
            ) : null}
            {orderingState.data && orderingState.data.ordering_status &&
            Array.isArray(orderingState.data.ordering_status.sample_deliverable_messages) &&
            orderingState.data.ordering_status.sample_deliverable_messages.length > 0 ? (
              <details style={{ marginTop: "0.75rem" }}>
                <summary>Sample Deliverable Messages</summary>
                <div className="messages">
                  {orderingState.data.ordering_status.sample_deliverable_messages.map((sample, index) => (
                    <div key={sample.msg_id || `sample-${index}`} className="message">
                      <div className="message-header">
                        <span>{sample.msg_id || "(no id)"}</span>
                        <span>{sample.sender || "unknown"}</span>
                      </div>
                      <div className="message-payload">
                        Corrected: {formatDate(sample.corrected_timestamp)}
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            ) : null}
            {forceDeliveryState.error ? <p className="error">{forceDeliveryState.error}</p> : null}
            {forceDeliveryState.result ? (
              <div className="success-box">
                <p>{forceDeliveryState.result.message || "Forced delivery executed"}</p>
                <p>Delivered: {valueOrFallback(forceDeliveryState.result.delivered_count, "0")}</p>
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
