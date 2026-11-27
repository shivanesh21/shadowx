import React, { useState, useEffect } from 'react';
import {
  Folder,
  File,
  Code2,
  GitCommit,
  Download,
  Copy,
  Check,
  ChevronRight,
  ChevronDown,
  Layers,
  Sparkles,
} from 'lucide-react';
import { fetchFiles, fetchFileContent, getZipDownloadUrl } from '../api/client';
import { FileChangedEvent } from '../types';

interface CodeViewProps {
  runId: string;
  diffEvents: FileChangedEvent[];
}

interface TreeNode {
  name: string;
  path: string;
  isFolder: boolean;
  children: Record<string, TreeNode>;
}

export const CodeView: React.FC<CodeViewProps> = ({ runId, diffEvents }) => {
  const [activeTab, setActiveTab] = useState<'files' | 'diffs'>('files');
  const [fileList, setFileList] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [fileContent, setFileContent] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [openFolders, setOpenFolders] = useState<Record<string, boolean>>({});

  // Fetch file list on load
  useEffect(() => {
    if (!runId) return;
    fetchFiles(runId)
      .then((files) => {
        setFileList(files);
        if (files.length > 0 && !selectedFile) {
          // Default to first src/ file or first file
          const defaultFile = files.find((f) => f.startsWith('src/')) || files[0];
          setSelectedFile(defaultFile);
        }
      })
      .catch(() => {});
  }, [runId]);

  // Fetch file content on file select
  useEffect(() => {
    if (!runId || !selectedFile) return;
    setLoading(true);
    fetchFileContent(runId, selectedFile)
      .then((res) => {
        setFileContent(res.content || '');
      })
      .catch(() => {
        setFileContent(`// Unable to read ${selectedFile}`);
      })
      .finally(() => setLoading(false));
  }, [runId, selectedFile]);

  // Build recursive tree from flat file list
  const buildTree = (paths: string[]): TreeNode => {
    const root: TreeNode = { name: 'root', path: '', isFolder: true, children: {} };
    paths.forEach((path) => {
      const parts = path.split('/');
      let curr = root;
      parts.forEach((part, idx) => {
        const isLast = idx === parts.length - 1;
        const currentPath = parts.slice(0, idx + 1).join('/');
        if (!curr.children[part]) {
          curr.children[part] = {
            name: part,
            path: currentPath,
            isFolder: !isLast,
            children: {},
          };
        }
        curr = curr.children[part];
      });
    });
    return root;
  };

  const toggleFolder = (folderPath: string) => {
    setOpenFolders((prev) => ({
      ...prev,
      [folderPath]: prev[folderPath] === undefined ? true : !prev[folderPath],
    }));
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(fileContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const renderTree = (node: TreeNode, depth: number = 0) => {
    const sortedChildren = Object.values(node.children).sort((a, b) => {
      if (a.isFolder === b.isFolder) return a.name.localeCompare(b.name);
      return a.isFolder ? -1 : 1;
    });

    return (
      <div className="space-y-0.5">
        {sortedChildren.map((child) => {
          if (child.isFolder) {
            const isOpen = openFolders[child.path] !== false; // default open
            return (
              <div key={child.path}>
                <button
                  onClick={() => toggleFolder(child.path)}
                  style={{ paddingLeft: `${depth * 12 + 8}px` }}
                  className="w-full text-left py-1 pr-2 rounded text-xs font-semibold text-gray-400 hover:text-gray-200 hover:bg-gray-900/60 flex items-center gap-1.5 transition-colors"
                >
                  {isOpen ? (
                    <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5 text-gray-500" />
                  )}
                  <Folder className="w-3.5 h-3.5 text-indigo-400" />
                  <span className="truncate">{child.name}</span>
                </button>
                {isOpen && renderTree(child, depth + 1)}
              </div>
            );
          }

          const isSelected = selectedFile === child.path;
          return (
            <button
              key={child.path}
              onClick={() => setSelectedFile(child.path)}
              style={{ paddingLeft: `${depth * 12 + 20}px` }}
              className={`w-full text-left py-1 pr-2 rounded text-xs font-mono flex items-center gap-2 transition-colors ${
                isSelected
                  ? 'bg-indigo-950/60 text-indigo-300 font-semibold border-l-2 border-indigo-500'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-900/40'
              }`}
            >
              <File className="w-3.5 h-3.5 text-gray-500 shrink-0" />
              <span className="truncate">{child.name}</span>
            </button>
          );
        })}
      </div>
    );
  };

  const fileTree = buildTree(fileList);

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-5 shadow-xl backdrop-blur-sm">
      {/* Top Bar: Tabs & Download ZIP */}
      <div className="flex items-center justify-between pb-3 border-b border-gray-800 mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('files')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors ${
              activeTab === 'files'
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-950 text-gray-400 hover:text-gray-200'
            }`}
          >
            <Code2 className="w-3.5 h-3.5" />
            <span>Workspace Files ({fileList.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('diffs')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors ${
              activeTab === 'diffs'
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-950 text-gray-400 hover:text-gray-200'
            }`}
          >
            <GitCommit className="w-3.5 h-3.5" />
            <span>Agent Diffs ({diffEvents.length})</span>
          </button>
        </div>

        <a
          href={getZipDownloadUrl(runId)}
          download
          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white flex items-center gap-1.5 shadow-lg shadow-indigo-600/20 transition-all"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Download Workspace ZIP</span>
        </a>
      </div>

      {/* Main Tab Content */}
      {activeTab === 'files' ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* File Tree Column */}
          <div className="md:col-span-1 bg-gray-950 border border-gray-800 rounded-lg p-3 max-h-[560px] overflow-y-auto">
            <div className="text-[11px] font-bold uppercase tracking-wider text-gray-400 mb-2 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-indigo-400" />
              <span>Workspace Tree</span>
            </div>
            {fileList.length === 0 ? (
              <div className="text-xs text-gray-500 py-6 text-center">
                No workspace files generated yet.
              </div>
            ) : (
              renderTree(fileTree)
            )}
          </div>

          {/* Code Viewer Column */}
          <div className="md:col-span-3 bg-gray-950 border border-gray-800 rounded-lg p-4 flex flex-col max-h-[560px]">
            {/* Viewer Header */}
            <div className="flex items-center justify-between pb-2 mb-3 border-b border-gray-800">
              <span className="font-mono text-xs text-gray-200 font-semibold truncate">
                {selectedFile || 'Select a file to inspect'}
              </span>
              {selectedFile && (
                <button
                  onClick={handleCopy}
                  className="px-2 py-1 rounded text-[11px] bg-gray-900 border border-gray-800 text-gray-400 hover:text-white flex items-center gap-1 transition-colors"
                >
                  {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>
              )}
            </div>

            {/* Code lines with line numbers */}
            <div className="flex-1 overflow-auto font-mono text-xs text-gray-300">
              {loading ? (
                <div className="text-center py-20 text-gray-500 animate-pulse">
                  Loading file...
                </div>
              ) : (
                <table className="w-full text-left border-collapse">
                  <tbody>
                    {fileContent.split('\n').map((line, idx) => (
                      <tr key={idx} className="hover:bg-gray-900/40">
                        <td className="w-10 pr-3 text-right text-gray-600 select-none text-[11px] align-top py-0.5">
                          {idx + 1}
                        </td>
                        <td className="pl-3 whitespace-pre text-gray-300 py-0.5 border-l border-gray-900">
                          {line}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* Diffs Tab Content */
        <div className="space-y-4 max-h-[560px] overflow-y-auto pr-1">
          {diffEvents.length === 0 ? (
            <div className="text-center py-16 text-xs text-gray-500">
              No file diff events recorded yet.
            </div>
          ) : (
            diffEvents.map((diff, idx) => (
              <div
                key={idx}
                className="rounded-lg border border-gray-800 bg-gray-950 overflow-hidden font-mono text-xs"
              >
                {/* Diff Header */}
                <div className="px-3 py-2 bg-gray-900/80 border-b border-gray-800 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <GitCommit className="w-3.5 h-3.5 text-amber-400" />
                    <span className="font-semibold text-white">{diff.path}</span>
                  </div>
                  {diff.agent_name && (
                    <span className="px-2 py-0.5 rounded text-[10px] bg-indigo-950 border border-indigo-700/50 text-indigo-300 flex items-center gap-1">
                      <Sparkles className="w-3 h-3 text-indigo-400" />
                      <span>Changed by {diff.agent_name}</span>
                    </span>
                  )}
                </div>

                {/* Diff Lines */}
                <div className="p-3 overflow-x-auto whitespace-pre text-[11px] space-y-0.5">
                  {diff.diff ? (
                    diff.diff.split('\n').map((line, lIdx) => {
                      let lineClass = 'text-gray-400';
                      if (line.startsWith('+')) {
                        lineClass = 'text-emerald-400 bg-emerald-950/30';
                      } else if (line.startsWith('-')) {
                        lineClass = 'text-rose-400 bg-rose-950/30';
                      } else if (line.startsWith('@@')) {
                        lineClass = 'text-cyan-400 font-bold';
                      }
                      return (
                        <div key={lIdx} className={`${lineClass} px-1 rounded`}>
                          {line}
                        </div>
                      );
                    })
                  ) : (
                    <span className="text-gray-500">File created or overwritten directly.</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
