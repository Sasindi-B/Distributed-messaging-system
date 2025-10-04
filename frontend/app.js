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
      const response = await fetch(url + "/messages");
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
  }, [baseUrl]);

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

    setSendState({ loading: true, error: null, success: null });
    try {
      const response = await fetch(url + "/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        throw new Error("Send request failed (" + response.status + ")");
      }
      await response.json();
      setSendState({ loading: false, error: null, success: "Message accepted by node" });
      setForm({ sender: "", recipient: "", payload: "", msg_id: "" });
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
                      <span>{senderLabel} -> {recipientLabel}</span>
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
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
