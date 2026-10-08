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

  // Helper: Extract domain from URL
  const getDomain = (url) => {
    try {
      return new URL(url).hostname;
    } catch {
      return null;
    }
  };

  // Parses structured duckduckgo output:
  // Title: ... \n URL: ... \n Snippet: ... \n ---
  const parseSearchResults = (content) => {
    if (!content) return [];
    if (content.includes('Title:') && content.includes('URL:')) {
      return content.split('---').map(item => {
        const lines = item.trim().split('\n');
        let title = '';
        let url = '';
        let snippet = '';
        lines.forEach(line => {
          if (line.startsWith('Title:')) {
            title = line.replace('Title:', '').trim();
          } else if (line.startsWith('URL:')) {
            url = line.replace('URL:', '').trim();
          } else if (line.startsWith('Snippet:')) {
            snippet = line.replace('Snippet:', '').trim();
          }
        });
        if (title || url || snippet) {
          return { title, url, snippet };
        }
        return null;
      }).filter(Boolean);
    }
    return [{ title: 'Web Search Result', snippet: content }];
  };

  // Custom regex markdown formatter
  const renderMarkdown = (text) => {
    if (!text) return null;
    const parts = [];
    const regex = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
    let lastIndex = 0;
    let match;
    
    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }
      
      const title = match[1];
      const url = match[2];
      
      parts.push(
        <a 
          key={match.index} 
          href={url} 
          target="_blank" 
          rel="noopener noreferrer"
          className="inline-citation"
        >
          {title} <ExternalLink style={{ width: '0.75rem', height: '0.75rem', display: 'inline', marginLeft: '2px' }} />
        </a>
      );
      
      lastIndex = regex.lastIndex;
    }
    
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }
    
    return (
      <div className="formatted-markdown">
        {parts.map((part, idx) => {
          if (typeof part === 'string') {
            return part.split('\n\n').map((para, pIdx) => {
              if (para.trim().startsWith('- ') || para.trim().startsWith('* ')) {
                return (
                  <ul key={`${idx}-${pIdx}`} className="markdown-list">
                    {para.split('\n').map((item, iIdx) => (
                      <li key={iIdx}>{item.replace(/^[-*]\s+/, '')}</li>
                    ))}
                  </ul>
                );
              }
              if (/^\d+\.\s+/.test(para.trim())) {
                return (
                  <ol key={`${idx}-${pIdx}`} className="markdown-ol">
                    {para.split('\n').map((item, iIdx) => (
                      <li key={iIdx}>{item.replace(/^\d+\.\s+/, '')}</li>
                    ))}
                  </ol>
                );
              }
              if (para.trim().startsWith('### ')) {
                return <h4 key={`${idx}-${pIdx}`} className="markdown-h4">{para.replace(/^###\s+/, '')}</h4>;
              }
              if (para.trim().startsWith('## ')) {
                return <h3 key={`${idx}-${pIdx}`} className="markdown-h3">{para.replace(/^##\s+/, '')}</h3>;
              }
              if (para.trim().startsWith('# ')) {
                return <h2 key={`${idx}-${pIdx}`} className="markdown-h2">{para.replace(/^#\s+/, '')}</h2>;
              }
              return <p key={`${idx}-${pIdx}`} className="markdown-para">{para}</p>;
            });
          }
          return part;
        })}
      </div>
    );
  };

  return (
    <div className={`app-wrapper ${sidebarOpen ? 'sidebar-expanded' : ''}`}>
      {/* Search History Sidebar */}
      <aside className={`history-sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-title">
            <History style={{ width: '1.1rem', height: '1.1rem', color: '#818cf8' }} />
            <span>Research History</span>
          </div>
          <button className="icon-btn close-sidebar-btn" onClick={() => setSidebarOpen(false)}>
            <X style={{ width: '1.25rem', height: '1.25rem' }} />
          </button>
        </div>
        
        <div className="sidebar-list">
          {history.length === 0 ? (
            <div className="sidebar-empty">
              <p>No past research yet</p>
            </div>
          ) : (
            history.map((entry) => (
              <div 
                key={entry.id} 
                className="sidebar-item" 
                onClick={() => loadHistoryEntry(entry)}
              >
                <div className="sidebar-item-content">
                  <div className="sidebar-item-query">{entry.query}</div>
                  <div className="sidebar-item-meta">
                    <span>Limit: {entry.maxSearches}</span>
                    <span>•</span>
                    <span>{entry.timestamp.split(',')[0]}</span>
                  </div>
                </div>
                <button 
                  className="sidebar-delete-btn" 
                  onClick={(e) => deleteHistoryEntry(entry.id, e)}
                  title="Delete query"
                >
                  <Trash2 style={{ width: '0.85rem', height: '0.85rem' }} />
                </button>
              </div>
            ))
          )}
        </div>

        {history.length > 0 && (
          <div className="sidebar-footer">
            <button className="clear-all-btn" onClick={clearAllHistory}>
              <Trash2 style={{ width: '0.95rem', height: '0.95rem' }} />
              Clear All
            </button>
          </div>
        )}
      </aside>

      {/* Main Container */}
      <main className="main-content">
        {/* Header */}
        <header className="app-header">
          <div className="header-actions">
            <button 
              className="icon-btn sidebar-toggle-btn" 
              onClick={() => setSidebarOpen(!sidebarOpen)}
              title="Toggle History"
            >
              <Menu style={{ width: '1.25rem', height: '1.25rem' }} />
            </button>
            <div style={{ flexGrow: 1 }} />
            <button 
              className="icon-btn theme-toggle-btn" 
              onClick={toggleTheme}
              title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            >
              {theme === 'dark' ? (
                <Sun style={{ width: '1.25rem', height: '1.25rem' }} />
              ) : (
                <Moon style={{ width: '1.25rem', height: '1.25rem' }} />
              )}
            </button>
          </div>
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
            {/* Ask Panel */}
            <div className="glass-panel">
              <h2 className="panel-title">
                <Search style={{ width: '1.25rem', height: '1.25rem', color: '#818cf8' }} />
                Ask Pathfinder
              </h2>
              <form onSubmit={handleSearch} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
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
                
                {/* Search Budget Slider */}
                <div className="slider-container">
                  <div className="slider-header">
                    <span>Search Limit Budget</span>
                    <span className="slider-value">{maxSearches} searches</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="8"
                    value={maxSearches}
                    onChange={(e) => setMaxSearches(parseInt(e.target.value))}
                    className="budget-slider"
                    disabled={searching}
                  />
                  <div className="slider-ticks">
                    {[1, 2, 3, 4, 5, 6, 7, 8].map(n => (
                      <span 
                        key={n} 
                        className={`tick ${n === maxSearches ? 'active' : ''}`}
                        onClick={() => !searching && setMaxSearches(n)}
                      >
                        {n}
                      </span>
                    ))}
                  </div>
                </div>

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
                <h3 className="panel-title-secondary">Search Progress</h3>
                <span className="budget-badge">
                  {currentLoopCount}/{maxSearches}
                </span>
              </div>
              
              {/* Horizontal indicators */}
              <div 
                className="budget-bar-container"
                style={{ gridTemplateColumns: `repeat(${maxSearches}, 1fr)` }}
              >
                {Array.from({ length: maxSearches }, (_, i) => i + 1).map((step) => {
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
                If Pathfinder requests more than {maxSearches} searches, the loop control automatically interrupts to synthesize results and avoid resource waste.
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
                              Search {log.loop_count}/{maxSearches}
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
                    const sources = parseSearchResults(log.content);

                    return (
                      <div key={index} className="log-card search-action">
                        <div className="log-card-icon-wrapper">
                          <RefreshCw style={{ width: '1rem', height: '1rem' }} />
                        </div>
                        <div className="log-card-content">
                          <div 
                            className="log-card-title" 
                            onClick={() => toggleExpand(index)} 
                            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', cursor: 'pointer' }}
                          >
                            <span style={{ flexGrow: 1 }}>Executed Web Search ({sources.length} sources found)</span>
                            {isExpanded ? <ChevronUp style={{ width: '1rem', height: '1rem' }} /> : <ChevronDown style={{ width: '1rem', height: '1rem' }} />}
                          </div>
                          <div className={`collapsible-content ${isExpanded ? 'expanded' : 'collapsed'}`}>
                            {isExpanded ? (
                              <div className="sources-container">
                                {sources.map((source, sIdx) => {
                                  const domain = getDomain(source.url);
                                  return (
                                    <div key={sIdx} className="source-card">
                                      <div className="source-header">
                                        {domain && (
                                          <img 
                                            src={`https://www.google.com/s2/favicons?domain=${domain}&sz=32`} 
                                            alt={domain} 
                                            className="source-favicon"
                                            onError={(e) => { e.target.style.display = 'none'; }}
                                          />
                                        )}
                                        {source.url ? (
                                          <a href={source.url} target="_blank" rel="noopener noreferrer" className="source-link">
                                            {source.title || domain || 'Source'}
                                            <ExternalLink style={{ width: '0.85rem', height: '0.85rem', marginLeft: '4px' }} />
                                          </a>
                                        ) : (
                                          <span className="source-no-link">{source.title || 'Source'}</span>
                                        )}
                                      </div>
                                      <p className="source-snippet">{source.snippet}</p>
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <p className="collapsed-preview-text">
                                {sources.map(s => s.title || getDomain(s.url)).filter(Boolean).join(' | ')}
                              </p>
                            )}
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
                <div className="panel-header-row" style={{ borderBottom: '1px solid rgba(16, 185, 129, 0.15)', paddingBottom: '0.75rem', marginBottom: '1rem' }}>
                  <h2 className="summary-title" style={{ marginBottom: 0 }}>
                    <CheckCircle2 style={{ width: '1.25rem', height: '1.25rem' }} />
                    Research Summary
                  </h2>
                  <div className="summary-actions">
                    <button className="toolbar-btn" onClick={copyToClipboard} title="Copy Summary">
                      {copied ? (
                        <>
                          <Check style={{ width: '0.95rem', height: '0.95rem', color: '#34d399' }} />
                          <span>Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy style={{ width: '0.95rem', height: '0.95rem' }} />
                          <span>Copy</span>
                        </>
                      )}
                    </button>
                    <button className="toolbar-btn" onClick={exportAsMarkdown} title="Export to Markdown">
                      <Download style={{ width: '0.95rem', height: '0.95rem' }} />
                      <span>Export</span>
                    </button>
                  </div>
                </div>
                <div className="summary-body">
                  {renderMarkdown(finalAnswer)}
                </div>
              </div>
            )}

          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
