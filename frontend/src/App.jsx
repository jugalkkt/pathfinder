import React, { useState, useEffect, useRef } from 'react';
import { 
  Compass, Search, Brain, HelpCircle, Loader2, Sparkles, AlertCircle, 
  RefreshCw, Terminal, CheckCircle2, ChevronDown, ChevronUp,
  Copy, Download, Moon, Sun, Trash2, History, Menu, X, Check, ExternalLink
} from 'lucide-react';

function App() {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [logs, setLogs] = useState([]);
  const [maxSearches, setMaxSearches] = useState(4);
  const [currentLoopCount, setCurrentLoopCount] = useState(0);
  const [finalAnswer, setFinalAnswer] = useState('');
  const [expandedResults, setExpandedResults] = useState({});
  const [copied, setCopied] = useState(false);
  const [history, setHistory] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [theme, setTheme] = useState('dark');
  
  const logsEndRef = useRef(null);

  // Initialize Theme and History
  useEffect(() => {
    const savedTheme = localStorage.getItem('pathfinder_theme') || 'dark';
    setTheme(savedTheme);
    document.documentElement.setAttribute('data-theme', savedTheme);

    const savedHistory = JSON.parse(localStorage.getItem('pathfinder_history')) || [];
    setHistory(savedHistory);
  }, []);

  // Auto-scroll logs to bottom
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Handle Theme Toggle
  const toggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
    document.documentElement.setAttribute('data-theme', nextTheme);
    localStorage.setItem('pathfinder_theme', nextTheme);
  };

  const handleSearch = (e) => {
    e.preventDefault();
    if (!query.trim() || searching) return;

    setSearching(true);
    setLogs([]);
    setCurrentLoopCount(0);
    setFinalAnswer('');
    setExpandedResults({});

    const eventSource = new EventSource(
      `http://127.0.0.1:8000/api/research?query=${encodeURIComponent(query)}&max_searches=${maxSearches}`
    );

    let finalLogs = [];

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'done') {
          setSearching(false);
          eventSource.close();
          const doneLog = { type: 'system', message: 'Research process finished successfully.' };
          setLogs(prev => {
            const updated = [...prev, doneLog];
            finalLogs = updated;
            // Save to history on completion
            saveToHistory(query, maxSearches, updated, data.content || finalAnswer);
            return updated;
          });
        } else if (data.type === 'error') {
          setSearching(false);
          eventSource.close();
          const errLog = { type: 'error', message: data.message };
          setLogs(prev => {
            const updated = [...prev, errLog];
            finalLogs = updated;
            saveToHistory(query, maxSearches, updated, '');
            return updated;
          });
        } else {
          setLogs(prev => {
            const updated = [...prev, data];
            finalLogs = updated;
            return updated;
          });
          if (data.loop_count !== undefined) {
            setCurrentLoopCount(data.loop_count);
          }
          if (data.type === 'chatbot_response' && data.content) {
            setFinalAnswer(data.content);
          }
        }
      } catch (err) {
        console.error("Error parsing message:", err);
      }
    };

    eventSource.onerror = (err) => {
      console.error("EventSource failed:", err);
      setSearching(false);
      const connErrLog = { type: 'error', message: 'Lost connection to backend server.' };
      setLogs(prev => {
        const updated = [...prev, connErrLog];
        saveToHistory(query, maxSearches, updated, '');
        return updated;
      });
      eventSource.close();
    };
  };

  // Save Search details to local history
  const saveToHistory = (searchQuery, budget, searchLogs, summaryText) => {
    // Avoid saving empty or redundant duplicates of identical query at same time
    const newEntry = {
      id: Date.now().toString(),
      query: searchQuery,
      maxSearches: budget,
      logs: searchLogs,
      finalAnswer: summaryText || finalAnswer,
      timestamp: new Date().toLocaleString()
    };
    
    setHistory(prev => {
      const updated = [newEntry, ...prev.filter(item => item.query !== searchQuery)].slice(0, 20); // cap at 20 searches
      localStorage.setItem('pathfinder_history', JSON.stringify(updated));
      return updated;
    });
  };

  const loadHistoryEntry = (entry) => {
    setQuery(entry.query);
    setMaxSearches(entry.maxSearches);
    setLogs(entry.logs);
    setFinalAnswer(entry.finalAnswer);
    const lastLog = entry.logs[entry.logs.length - 1];
    setCurrentLoopCount(
      entry.logs.reduce((acc, log) => (log.loop_count !== undefined ? Math.max(acc, log.loop_count) : acc), 0)
    );
    setSidebarOpen(false);
  };

  const deleteHistoryEntry = (id, e) => {
    e.stopPropagation();
    setHistory(prev => {
      const updated = prev.filter(entry => entry.id !== id);
      localStorage.setItem('pathfinder_history', JSON.stringify(updated));
      return updated;
    });
  };

  const clearAllHistory = () => {
    if (window.confirm("Are you sure you want to clear your search history?")) {
      localStorage.removeItem('pathfinder_history');
      setHistory([]);
    }
  };

  const copyToClipboard = () => {
    if (!finalAnswer) return;
    navigator.clipboard.writeText(finalAnswer);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const exportAsMarkdown = () => {
    if (!finalAnswer) return;
    
    let mdContent = `# Pathfinder AI Research Report\n`;
    mdContent += `*Generated on: ${new Date().toLocaleString()}*\n\n`;
    mdContent += `## Query\n> ${query}\n\n`;
    mdContent += `## Research Summary\n\n${finalAnswer}\n\n`;
    mdContent += `## Thought Process Logs\n\n`;
    
    logs.forEach(log => {
      if (log.type === 'search_start') {
        mdContent += `### [Reasoning Loop - Search ${log.loop_count}/${maxSearches}]\n`;
        mdContent += `Formulating query: \`${log.query}\`\n\n`;
      } else if (log.type === 'search_result') {
        mdContent += `### [Action - Web Search Result]\n`;
        mdContent += `\`\`\`\n${log.content}\n\`\`\`\n\n`;
      } else if (log.type === 'system') {
        mdContent += `*System: ${log.message}*\n\n`;
      } else if (log.type === 'error') {
        mdContent += `*Error: ${log.message}*\n\n`;
      }
    });

    const blob = new Blob([mdContent], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `pathfinder_research_${Date.now()}.md`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const toggleExpand = (index) => {
    setExpandedResults(prev => ({
      ...prev,
      [index]: !prev[index]
    }));
  };

  return (
    <div>
      {/* Header */}
      <header className="app-header">
        <div className="logo-container">
          <Compass style={{ width: '2.25rem', height: '2.25rem' }} />
        </div>
        <h1 className="app-title">Pathfinder 2.0</h1>
        <p className="app-subtitle">
          Autonomous Web Research Assistant with Real-time Thought Process Mapping
        </p>
      </header>

      {/* Main Grid */}
      <div className="dashboard-grid">
        
        {/* Left Column: Query Panel & Loop Tracker */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="glass-panel">
            <h2 className="panel-title">
              <Search style={{ width: '1.25rem', height: '1.25rem', color: '#818cf8' }} />
              Ask Pathfinder
            </h2>
            <form onSubmit={handleSearch} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask a question..."
                rows="4"
                className="query-textarea"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSearch(e);
                  }
                }}
              />
              <button
                type="submit"
                disabled={searching || !query.trim()}
                className="glow-btn"
              >
                {searching ? (
                  <>
                    <Loader2 style={{ width: '1rem', height: '1rem', animation: 'spin 1s linear infinite' }} />
                    Searching...
                  </>
                ) : (
                  <>
                    <Sparkles style={{ width: '1rem', height: '1rem' }} />
                    Research Query
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Loop Tracker */}
          <div className="glass-panel">
            <div className="panel-header-row">
              <h3 className="panel-title-secondary">Search Limit Budget</h3>
              <span className="budget-badge">
                {currentLoopCount}/4
              </span>
            </div>
            
            {/* Horizontal indicators */}
            <div className="budget-bar-container">
              {[1, 2, 3, 4].map((step) => {
                const isActive = currentLoopCount >= step;
                const isCurrent = currentLoopCount === step && searching;
                return (
                  <div
                    key={step}
                    className={`budget-bar ${isActive ? 'active' : ''} ${isCurrent ? 'pulse' : ''}`}
                  />
                );
              })}
            </div>

            <p className="budget-desc">
              If Pathfinder requests more than 4 searches, loop control automatically interrupts to synthesize results and avoid resource waste.
            </p>
          </div>
        </div>

        {/* Right Column: Execution Log & Output */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          
          {/* Live Logs */}
          <div className="glass-panel terminal-logs">
            <div className="panel-header-row">
              <h2 className="panel-title-secondary">
                <Terminal style={{ width: '1.25rem', height: '1.25rem', color: '#818cf8', marginRight: '0.4rem' }} />
                Research Thought Process
              </h2>
              {searching && (
                <span className="live-badge">
                  <span className="live-badge-dot" />
                  Live Stream
                </span>
              )}
            </div>

            <div className="logs-container">
              {logs.length === 0 && !searching && (
                <div className="empty-state">
                  <HelpCircle className="empty-state-icon" />
                  <p>Submit a query above to trace Pathfinder's actions in real time.</p>
                </div>
              )}

              {logs.map((log, index) => {
                if (log.type === 'search_start') {
                  return (
                    <div key={index} className="log-card reasoning">
                      <div className="log-card-icon-wrapper">
                        <Brain style={{ width: '1rem', height: '1rem' }} />
                      </div>
                      <div className="log-card-content">
                        <div className="log-card-title">
                          Reasoning Loop
                          <span className="budget-badge">
                            Search {log.loop_count}/4
                          </span>
                        </div>
                        <div className="log-card-body">
                          Formulating query: <span className="code-badge">{log.query}</span>
                        </div>
                      </div>
                    </div>
                  );
                }

                if (log.type === 'search_result') {
                  const isExpanded = expandedResults[index];
                  return (
                    <div key={index} className="log-card search-action">
                      <div className="log-card-icon-wrapper">
                        <RefreshCw style={{ width: '1rem', height: '1rem' }} />
                      </div>
                      <div className="log-card-content">
                        <div className="log-card-title" onClick={() => toggleExpand(index)} style={{ display: 'flex', justifyContent: 'between', alignItems: 'center', width: '100%' }}>
                          <span style={{ flexGrow: 1 }}>Executed Web Search</span>
                          {isExpanded ? <ChevronUp style={{ width: '1rem', height: '1rem' }} /> : <ChevronDown style={{ width: '1rem', height: '1rem' }} />}
                        </div>
                        <div className={`collapsible-content ${isExpanded ? '' : 'collapsed'}`}>
                          {log.content}
                        </div>
                      </div>
                    </div>
                  );
                }

                if (log.type === 'chatbot_response' && searching) {
                  return (
                    <div key={index} className="log-card reasoning">
                      <div className="log-card-icon-wrapper">
                        <Brain style={{ width: '1rem', height: '1rem' }} />
                      </div>
                      <div className="log-card-content">
                        <div className="log-card-title">Synthesizing Information</div>
                        <div className="log-card-body" style={{ fontStyle: 'italic', color: '#94a3b8' }}>
                          Pathfinder is digesting the search results and compiling notes...
                        </div>
                      </div>
                    </div>
                  );
                }

                if (log.type === 'system') {
                  return (
                    <div key={index} className="log-card system">
                      <div className="log-card-icon-wrapper">
                        <CheckCircle2 style={{ width: '1rem', height: '1rem' }} />
                      </div>
                      <div className="log-card-content">
                        <div className="log-card-body" style={{ fontWeight: '500' }}>
                          {log.message}
                        </div>
                      </div>
                    </div>
                  );
                }

                if (log.type === 'error') {
                  return (
                    <div key={index} className="log-card error">
                      <div className="log-card-icon-wrapper">
                        <AlertCircle style={{ width: '1rem', height: '1rem' }} />
                      </div>
                      <div className="log-card-content">
                        <div className="log-card-body" style={{ fontWeight: '500' }}>
                          {log.message}
                        </div>
                      </div>
                    </div>
                  );
                }

                return null;
              })}
              <div ref={logsEndRef} />
            </div>
          </div>

          {/* Final Output Summary */}
          {finalAnswer && (
            <div className="summary-panel animate-slide-in">
              <h2 className="summary-title">
                <CheckCircle2 style={{ width: '1.25rem', height: '1.25rem' }} />
                Research Summary
              </h2>
              <div className="summary-body">
                {finalAnswer}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

export default App;
