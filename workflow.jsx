import React, { useState } from 'react';
import { 
  Folder, 
  FileText, 
  ChevronRight, 
  ChevronDown, 
  Zap, 
  RefreshCcw, 
  Database, 
  Search, 
  PlusCircle, 
  Layers, 
  ShieldAlert, 
  Settings,
  ArrowRight,
  Info,
  CheckCircle2,
  FileSearch,
  LayoutTemplate,
  History,
  Lock,
  Users
} from 'lucide-react';

const App = () => {
  const [activeTab, setActiveTab] = useState('greenfield');
  const [selectedAgent, setSelectedAgent] = useState(null);

  const tiers = [
    { id: 1, name: 'Tier 1: CLAUDE.md', desc: 'Auto-loaded every session. The map of the project.', color: 'bg-blue-500' },
    { id: 2, name: 'Tier 2: docs/context/', desc: 'Hot tier. Frequent, dense context loaded at session start.', color: 'bg-orange-500' },
    { id: 3, name: 'Tier 3: Everything Else', desc: 'Cold tier. Pulled on-demand when directly relevant.', color: 'bg-slate-400' },
  ];

  const agents = {
    greenfield: [
      {
        id: 'scaffolding',
        name: 'Scaffolding Agent',
        icon: <LayoutTemplate className="w-5 h-5" />,
        trigger: 'Project Start',
        input: 'Project Description',
        output: 'Folder structure + Empty templates + Starter CLAUDE.md',
        details: 'Creates the skeletal structure with frontmatter-ready files.'
      },
      {
        id: 'drafting',
        name: 'Document Drafting Agent',
        icon: <PlusCircle className="w-5 h-5" />,
        trigger: 'Developer Intent',
        input: 'Specific prompt describing intent',
        output: 'Fully drafted SPEC, PLAN, or ARCH file',
        details: 'Handles the heavy lifting of writing content based on your technical goals.'
      },
      {
        id: 'sync',
        name: 'CLAUDE.md Sync Agent',
        icon: <RefreshCcw className="w-5 h-5" />,
        trigger: 'File System Change',
        input: 'Current docs/ state',
        output: 'Updated CLAUDE.md Map section',
        details: 'Keeps the "Map" current by indexing all active files and their roles.'
      }
    ],
    migration: [
      {
        id: 'inventory',
        name: 'Inventory Agent',
        icon: <Search className="w-5 h-5" />,
        trigger: 'Migration Start',
        input: 'Existing codebase / Unstructured docs',
        output: 'Manifest of existing documents and types',
        details: 'Discovers existing ad-hoc documentation without modifying files.'
      },
      {
        id: 'indexing',
        name: 'Indexing Agent',
        icon: <Database className="w-5 h-5" />,
        trigger: 'Post-Inventory',
        input: 'Manifest + Un-indexed documents',
        output: 'Files moved to docs/ with YAML frontmatter injected',
        details: 'Converts un-indexed "organic" markdown into structured, searchable context.'
      },
      {
        id: 'gap',
        name: 'Gap Analysis Agent',
        icon: <ShieldAlert className="w-5 h-5" />,
        trigger: 'Post-Indexing',
        input: 'Current indexed document set',
        output: 'Prioritized list of missing docs (e.g., CONSTRAINTS.md)',
        details: 'Identifies weaknesses in the current knowledge base.'
      }
    ]
  };

  const TreeItem = ({ icon: Icon, name, color = "text-slate-600", tier, unindexed, children }) => (
    <div className="ml-4">
      <div className={`flex items-center gap-2 py-1 px-2 rounded hover:bg-slate-100 transition-colors cursor-default group ${unindexed ? 'border-l-2 border-dashed border-red-300 bg-red-50/30' : ''}`}>
        <Icon className={`w-4 h-4 ${color}`} />
        <span className={`text-sm ${unindexed ? 'text-red-700 italic font-medium' : 'text-slate-800'}`}>{name}</span>
        {tier && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full text-white font-bold
            ${tier === 1 ? 'bg-blue-500' : tier === 2 ? 'bg-orange-500' : 'bg-slate-400'}`}>
            T{tier}
          </span>
        )}
        {unindexed && <span className="text-[10px] text-red-500 font-bold uppercase ml-auto">Un-indexed</span>}
      </div>
      {children && <div className="ml-2 border-l border-slate-200">{children}</div>}
    </div>
  );

  return (
    <div className="flex flex-col h-screen bg-slate-50 text-slate-900 font-sans p-6 overflow-hidden">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Zap className="text-indigo-600 fill-indigo-600" />
            Claude Code Workflow Architecture
          </h1>
          <p className="text-slate-500 text-sm">Visualizing the Document-Backed Development Lifecycle</p>
        </div>
        
        <div className="flex bg-slate-200 p-1 rounded-lg">
          <button 
            onClick={() => setActiveTab('greenfield')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${activeTab === 'greenfield' ? 'bg-white shadow-sm text-indigo-600' : 'text-slate-600 hover:text-slate-900'}`}
          >
            Greenfield Path
          </button>
          <button 
            onClick={() => setActiveTab('migration')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${activeTab === 'migration' ? 'bg-white shadow-sm text-indigo-600' : 'text-slate-600 hover:text-slate-900'}`}
          >
            Migration Path
          </button>
        </div>
      </div>

      <div className="flex flex-1 gap-6 min-h-0">
        
        {/* Left Column: File Structure */}
        <div className="flex-1 bg-white rounded-xl shadow-sm border border-slate-200 flex flex-col min-h-0">
          <div className="p-4 border-b border-slate-100 flex justify-between items-center">
            <h2 className="font-semibold text-slate-700 flex items-center gap-2">
              <Folder className="w-5 h-5 text-indigo-500" />
              Target Repository Structure
            </h2>
            <div className="flex gap-2">
              {tiers.map(t => (
                <div key={t.id} title={t.desc} className="flex items-center gap-1 cursor-help">
                   <div className={`w-2 h-2 rounded-full ${t.color}`} />
                   <span className="text-[10px] text-slate-400 font-bold">T{t.id}</span>
                </div>
              ))}
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
            <div className="space-y-1">
              <div className="flex items-center gap-2 mb-4 p-2 bg-indigo-50 rounded-lg border border-indigo-100">
                <Folder className="w-5 h-5 text-indigo-600" />
                <span className="font-bold text-slate-800">repo-root/</span>
              </div>
              
              <TreeItem icon={FileText} name="CLAUDE.md" tier={1} color="text-blue-600 font-bold" />
              
              <TreeItem icon={Folder} name="prompts/" color="text-indigo-400">
                <TreeItem icon={Lock} name="personal/" />
                <TreeItem icon={Users} name="managed/" />
                <TreeItem icon={History} name="history/" />
              </TreeItem>
              
              <TreeItem icon={Folder} name="docs/" color="text-indigo-400">
                <div className="ml-4 mb-2 p-2 bg-orange-50 border border-orange-100 rounded-lg">
                  <TreeItem icon={Folder} name="context/" color="text-orange-500 font-bold" tier={2}>
                    <TreeItem icon={FileText} name="BRIEF.md" />
                    <TreeItem icon={FileText} name="CONVENTIONS.md" />
                    <TreeItem icon={FileText} name="CONSTRAINTS.md" />
                    <TreeItem icon={FileText} name="GLOSSARY.md" />
                    <TreeItem icon={FileText} name="SCHEMA.md" />
                  </TreeItem>
                </div>
                
                <TreeItem icon={Folder} name="decisions/" tier={3}>
                  <TreeItem icon={FileText} name="0001-architecture.md" />
                  <TreeItem icon={FileText} name="0002-database-choice.md" />
                </TreeItem>
                
                <TreeItem icon={Folder} name="specs/" tier={3}>
                  <TreeItem icon={Folder} name="active/" />
                  <TreeItem icon={Folder} name="archive/" />
                </TreeItem>
                
                <TreeItem icon={Folder} name="plans/" tier={3}>
                  <TreeItem icon={Folder} name="active/" />
                </TreeItem>

                <TreeItem icon={FileText} name="runbooks.md" tier={3} />
                <TreeItem icon={FileText} name="changelog.md" tier={3} />
                
                {activeTab === 'migration' && (
                  <div className="mt-4 pt-4 border-t border-slate-100">
                    <TreeItem icon={FileText} name="old-notes.md" unindexed />
                    <TreeItem icon={FileText} name="Legacy_Doc_v2.txt" unindexed />
                  </div>
                )}
              </TreeItem>
            </div>
          </div>

          <div className="p-4 bg-slate-50 border-t border-slate-100">
             <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">YAML Frontmatter (The Index)</h3>
             <pre className="text-[10px] bg-slate-800 text-slate-300 p-2 rounded leading-relaxed">
{`---
type: SPEC | PLAN | ARCH | ADR ...
status: draft | active | superseded
claude-priority: high | low | never
---`}
             </pre>
          </div>
        </div>

        {/* Right Column: Workflow / Agents */}
        <div className="flex-1 flex flex-col gap-6">
          
          {/* Agent Pipeline */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 relative overflow-hidden">
             <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none">
                <Layers className="w-24 h-24 text-indigo-600" />
             </div>
             
             <h2 className="font-semibold text-slate-700 mb-6 flex items-center gap-2">
               <Settings className="w-5 h-5 text-indigo-500 animate-spin-slow" />
               Agent Orchestration Pipeline
             </h2>

             <div className="space-y-4 relative z-10">
                {agents[activeTab].map((agent, idx) => (
                  <div key={agent.id} className="relative">
                    <div 
                      onClick={() => setSelectedAgent(agent)}
                      className={`
                        p-4 rounded-xl border transition-all cursor-pointer group
                        ${selectedAgent?.id === agent.id 
                          ? 'border-indigo-500 bg-indigo-50 shadow-md ring-2 ring-indigo-200' 
                          : 'border-slate-200 bg-white hover:border-indigo-300 hover:shadow-sm'}
                      `}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <div className={`p-2 rounded-lg ${selectedAgent?.id === agent.id ? 'bg-indigo-500 text-white' : 'bg-slate-100 text-slate-500 group-hover:bg-indigo-100 group-hover:text-indigo-600'}`}>
                            {agent.icon}
                          </div>
                          <div>
                            <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Agent {idx + 1}</p>
                            <h3 className="font-bold text-slate-800">{agent.name}</h3>
                          </div>
                        </div>
                        <ChevronRight className={`w-5 h-5 transition-transform ${selectedAgent?.id === agent.id ? 'translate-x-1 text-indigo-600' : 'text-slate-300'}`} />
                      </div>
                    </div>
                    {idx < agents[activeTab].length - 1 && (
                      <div className="flex justify-center my-1">
                        <ArrowRight className="w-5 h-5 text-slate-300 rotate-90" />
                      </div>
                    )}
                  </div>
                ))}

                {/* The Loop Back */}
                <div className="mt-8 flex items-center justify-center">
                   <div className="flex flex-col items-center gap-2 p-4 border border-dashed border-indigo-200 rounded-xl bg-indigo-50/30 w-full">
                      <div className="flex items-center gap-2 text-indigo-600 font-bold text-sm">
                        <RefreshCcw className="w-4 h-4" />
                        Continuous Lifecycle Loop
                      </div>
                      <p className="text-xs text-slate-500 text-center">
                        Drafting and Syncing repeat indefinitely as the codebase evolves.
                      </p>
                   </div>
                </div>
             </div>
          </div>

          {/* Details Pane */}
          <div className="flex-1 bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col">
            {!selectedAgent ? (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-400 space-y-4">
                <Info className="w-10 h-10 opacity-20" />
                <p className="text-sm italic">Select an agent to view inputs, outputs, and specific workflow logic.</p>
              </div>
            ) : (
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="flex items-center gap-3 mb-6">
                   <div className="p-2 bg-indigo-100 text-indigo-600 rounded-lg">
                    {selectedAgent.icon}
                   </div>
                   <h3 className="text-xl font-bold text-slate-800">{selectedAgent.name}</h3>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-[10px] font-bold text-slate-400 uppercase mb-1">Input Source</h4>
                      <div className="flex items-center gap-2 text-sm text-slate-700 bg-slate-50 p-2 rounded border border-slate-100">
                        <FileSearch className="w-4 h-4 text-slate-400" />
                        {selectedAgent.input}
                      </div>
                    </div>
                    <div>
                      <h4 className="text-[10px] font-bold text-slate-400 uppercase mb-1">Trigger Event</h4>
                      <div className="flex items-center gap-2 text-sm text-indigo-700 bg-indigo-50 p-2 rounded border border-indigo-100">
                        <Zap className="w-4 h-4 text-indigo-400" />
                        {selectedAgent.trigger}
                      </div>
                    </div>
                  </div>
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-[10px] font-bold text-slate-400 uppercase mb-1">Core Output</h4>
                      <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 p-2 rounded border border-emerald-100">
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                        {selectedAgent.output}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-6 p-4 bg-slate-50 rounded-lg border border-slate-100">
                   <h4 className="text-xs font-bold text-slate-600 mb-2">Workflow Strategy</h4>
                   <p className="text-sm text-slate-600 leading-relaxed">
                     {selectedAgent.details}
                   </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`
        .animate-spin-slow {
          animation: spin 8s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #e2e8f0;
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #cbd5e1;
        }
      `}</style>
    </div>
  );
};

export default App;