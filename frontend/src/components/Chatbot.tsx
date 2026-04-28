import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { chatApi, authApi } from '../services/api';
import { Send, Plus, Settings, Trash2, Edit2, User, LogOut } from 'lucide-react';

interface Message {
  id: number;
  text: string;
  sender: 'user' | 'bot';
  type?: 'plain' | 'mcq';
  data?: any;
}

const Chatbot = () => {
  const [messages, setMessages] = useState<Message[]>([
    { id: 1, text: "Hi  Bestie! How Can I Help?", sender: 'bot' }
  ]);
  const [history, setHistory] = useState<any[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<number | null>(null);
  const conversationIdRef = useRef<number | null>(null);
  
  // Keep ref in sync with state
  useEffect(() => {
    conversationIdRef.current = currentConversationId;
  }, [currentConversationId]);

  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const username = localStorage.getItem('username') || 'User';

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const fetchHistory = async () => {
    try {
      const response = await chatApi.getHistory();
      setHistory(response.data);
    } catch (err) {
      console.error('Failed to fetch history', err);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Handle browser back button to logout
  useEffect(() => {
    const handleBackButton = () => {
      console.log("Back button detected, logging out...");
      handleLogout();
    };

    window.addEventListener('popstate', handleBackButton);
    
    return () => {
      window.removeEventListener('popstate', handleBackButton);
    };
  }, []);

  const handleClearHistory = async () => {
    if (window.confirm('Are you sure you want to clear all chat history?')) {
      try {
        await chatApi.clearHistory();
        setHistory([]);
        handleNewChat(); // Reset current chat view
      } catch (err) {
        console.error('Failed to clear history', err);
      }
    }
  };

  const handleDeleteConversation = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation(); // Prevent loading the conversation when clicking delete
    if (window.confirm('Are you sure you want to delete this chat?')) {
      try {
        await chatApi.deleteConversation(id);
        setHistory(prev => prev.filter(item => item.id !== id));
        if (currentConversationId === id) {
          handleNewChat();
        }
      } catch (err) {
        console.error('Failed to delete conversation', err);
      }
    }
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch (err) {
      console.error('Logout failed', err);
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('username');
      navigate('/login');
    }
  };

  const loadConversation = async (item: any) => {
    setCurrentConversationId(item.id);
    setLoading(true);
    try {
      const response = await chatApi.getConversationMessages(item.id);
      const conversationMessages: Message[] = [];
      
      response.data.forEach((msg: any) => {
        // Add User Message
        conversationMessages.push({
          id: msg.id * 2, // Ensure unique IDs
          text: msg.question,
          sender: 'user'
        });

        // Add Bot Response
        const botData = msg.response;
        let botText = '';
        if (botData.type === 'plain') {
          botText = botData.response;
        } else {
          botText = `Correct Answer: (${botData.best_option}) ${botData.correct_answer}\n\nExplanation: ${botData.explanation}`;
        }
        
        conversationMessages.push({
          id: msg.id * 2 + 1,
          text: botText,
          sender: 'bot',
          type: botData.type,
          data: botData
        });
      });

      setMessages(conversationMessages);
    } catch (err) {
      console.error('Failed to load conversation', err);
    } finally {
      setLoading(false);
    }
  };

  const handleNewChat = () => {
    setCurrentConversationId(null);
    setMessages([
      { id: 1, text: "Hello! I'm your Science Assistant. Ask me anything about science topics like erosion, circuits, or rocks!", sender: 'bot' }
    ]);
    setInput('');
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    // Use a ref to capture the absolute latest ID
    const activeConversationId = conversationIdRef.current;
    console.log('DEBUG: handleSend - activeConversationId from ref:', activeConversationId);

    const userMessage: Message = {
      id: Date.now(),
      text: input,
      sender: 'user'
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      console.log('DEBUG: chatApi.ask - sending question:', input, 'with conversation_id:', activeConversationId);
      const response = await chatApi.ask(input, activeConversationId || undefined);
      const botData = response.data;
      console.log('DEBUG: chatApi.ask - received botData:', botData);
      
      // Update the current conversation ID if it was a new one
      if (!activeConversationId && botData.conversation_id) {
        console.log('DEBUG: Setting new currentConversationId:', botData.conversation_id);
        setCurrentConversationId(botData.conversation_id);
      }

      let botText = '';
      if (botData.type === 'plain') {
        botText = botData.response;
      } else {
        botText = `Correct Answer: (${botData.best_option}) ${botData.correct_answer}\n\nExplanation: ${botData.explanation}`;
      }

      const botMessage: Message = {
        id: Date.now() + 1,
        text: botText,
        sender: 'bot',
        type: botData.type,
        data: botData
      };

      setMessages(prev => [...prev, botMessage]);
      fetchHistory(); // Refresh sidebar history
    } catch (err: any) {
      const errorMsg = err.response?.status === 401 ? 'Session expired. Please login again.' : 'Failed to get response. Please try again.';
      setMessages(prev => [...prev, { id: Date.now() + 1, text: errorMsg, sender: 'bot' }]);
      if (err.response?.status === 401) {
        setTimeout(() => navigate('/login'), 2000);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full bg-[#f8faff] overflow-hidden font-sans">
      {/* Sidebar */}
      <div className="flex w-72 flex-col bg-white p-6 shadow-sm border-r border-gray-100">
        <div className="mb-10 text-2xl font-black tracking-tight text-slate-800">CHAT A.I+</div>
        
        <button 
          onClick={handleNewChat}
          className="flex items-center justify-center gap-2 rounded-xl bg-black py-3.5 text-sm font-semibold text-white transition-all hover:bg-gray-800 shadow-md"
        >
          <Plus size={18} />
          <span>New chat</span>
        </button>

        <div className="mt-8 flex flex-col gap-1 overflow-y-auto">
          <div className="mb-4 flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-gray-400">
            <span>Your conversations</span>
            <button className="hover:text-black" onClick={handleClearHistory}>Clear All</button>
          </div>
          
          {history.length === 0 ? (
            <div className="px-3 py-4 text-xs text-gray-400 italic text-center">
              No past conversations
            </div>
          ) : (
            history.map((item, i) => (
              <div 
                key={item.id} 
                onClick={() => loadConversation(item)}
                className={`group flex items-center justify-between rounded-xl px-3 py-3 text-sm transition-all cursor-pointer ${item.id === currentConversationId ? 'bg-[#f0f4ff] text-blue-600 font-medium' : 'text-gray-500 hover:bg-gray-50'}`}
              >
                <div className="flex items-center gap-3 truncate">
                  <div className={`h-1.5 w-1.5 rounded-full ${item.id === currentConversationId ? 'bg-blue-500' : 'bg-transparent group-hover:bg-blue-400'}`}></div>
                  <span className="truncate">{item.title || item.question}</span>
                </div>
                <div className="hidden group-hover:flex items-center gap-1.5">
                  <Trash2 
                    size={14} 
                    className="text-gray-400 hover:text-red-500" 
                    onClick={(e) => handleDeleteConversation(e, item.id)}
                  />
                  <Edit2 size={14} className="text-gray-400 hover:text-blue-500" />
                </div>
              </div>
            ))
          )}
        </div>

        <div className="mt-auto space-y-2 pt-6">
          <button className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm text-gray-600 hover:bg-gray-50">
            <Settings size={18} />
            <span>Settings</span>
          </button>
          <div className="flex items-center justify-between border-t border-gray-100 pt-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-600">
                <User size={20} />
              </div>
              <div className="flex flex-col overflow-hidden">
                <span className="text-sm font-bold text-slate-800 truncate">{username}</span>
              </div>
            </div>
            <button onClick={handleLogout} className="p-2 text-gray-400 hover:text-red-500 transition-colors">
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex flex-1 flex-col relative">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-10 pb-32 pt-10">
          <div className="mx-auto max-w-4xl space-y-10 py-4">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex w-full ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`flex max-w-[85%] gap-4 ${msg.sender === 'user' ? 'flex-row-reverse' : ''}`}>
                  <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white shadow-sm ${msg.sender === 'user' ? 'bg-blue-600' : 'bg-slate-800'}`}>
                    {msg.sender === 'user' ? <User size={18} /> : <div className="text-[10px] font-bold">AI</div>}
                  </div>
                  <div className={`flex flex-col gap-2 ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                    <div className="text-[11px] font-bold uppercase tracking-widest text-gray-400">
                      {msg.sender === 'user' ? 'YOU' : 'CHAT A.I+'}
                    </div>
                    <div className={`rounded-2xl px-5 py-4 text-[15px] leading-relaxed shadow-sm ${msg.sender === 'user' ? 'bg-blue-600 text-white rounded-tr-none' : 'bg-white text-slate-700 rounded-tl-none border border-gray-50'}`}>
                      <div className="whitespace-pre-wrap">{msg.text}</div>
                      
                      {msg.sender === 'bot' && msg.data?.match_confidence !== undefined && (
                        <div className="mt-3 flex items-center gap-2">
                          <div className={`h-1.5 w-1.5 rounded-full ${msg.data.source === 'DeepSeek-R1' ? 'bg-purple-400' : 'bg-green-400'}`}></div>
                          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                            {msg.data.source || 'AI'}: {(msg.data.match_confidence * 100).toFixed(1)}%
                          </span>
                        </div>
                      )}

                      {msg.data?.type === 'mcq' && (
                        <div className="mt-4 space-y-2 border-t border-gray-50 pt-4">
                          {Object.entries(msg.data.options).map(([letter, opt]: [string, any]) => (
                            <div key={letter} className={`flex items-center gap-3 rounded-lg border p-2.5 text-sm transition-colors ${letter === msg.data.best_option ? 'border-green-200 bg-green-50 text-green-700' : 'border-gray-100'}`}>
                              <span className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ${letter === msg.data.best_option ? 'bg-green-500 text-white' : 'bg-gray-100 text-gray-500'}`}>
                                {letter}
                              </span>
                              <span>{opt.text}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="flex gap-4 items-center">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-800 text-white">
                    <div className="text-[10px] font-bold animate-pulse">AI</div>
                  </div>
                  <div className="flex gap-1">
                    <div className="h-2 w-2 rounded-full bg-blue-400 animate-bounce"></div>
                    <div className="h-2 w-2 rounded-full bg-blue-400 animate-bounce [animation-delay:-.3s]"></div>
                    <div className="h-2 w-2 rounded-full bg-blue-400 animate-bounce [animation-delay:-.5s]"></div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 w-full px-10 pb-8 bg-gradient-to-t from-[#f8faff] via-[#f8faff] to-transparent pt-10">
          <form onSubmit={handleSend} className="mx-auto max-w-4xl relative group">
            <input
              type="text"
              placeholder="What's in your mind?..."
              className="w-full rounded-2xl bg-white border border-gray-100 px-6 py-5 pr-16 text-slate-700 shadow-xl outline-none transition-all focus:border-blue-200 group-hover:shadow-2xl"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="absolute right-3 top-1/2 -translate-y-1/2 flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600 text-white shadow-lg transition-all hover:bg-blue-700 hover:scale-105 active:scale-95 disabled:bg-gray-300 disabled:shadow-none disabled:scale-100"
            >
              <Send size={20} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Chatbot;
