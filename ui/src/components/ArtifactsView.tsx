import React, { useState, useEffect } from 'react';
import {
  FileText,
  Compass,
  ShieldCheck,
  BookOpen,
  Copy,
  Check,
  Download,
  Code2,
  FileBox,
  Eye,
} from 'lucide-react';
import { fetchFileContent } from '../api/client';

interface ArtifactsViewProps {
  runId: string;
}

interface ArtifactMeta {
  id: string;
  label: string;
  stage: string;
  role: string;
  path: string;
  icon: React.ElementType;
}

const DEFAULT_ARTIFACTS: ArtifactMeta[] = [
  {
    id: 'requirements',
    label: 'Requirements Document',
    stage: 'ANALYSIS',
    role: 'Analyst',
    path: 'docs/requirements.md',
    icon: FileText,
  },
  {
    id: 'design',
    label: 'Design & Architecture',
    stage: 'DESIGN',
    role: 'Architect',
    path: 'docs/design.md',
    icon: Compass,
  },
  {
    id: 'review',
    label: 'Review & Traceability',
    stage: 'REVIEW',
    role: 'Reviewer',
    path: 'docs/review.md',
    icon: ShieldCheck,
  },
  {
    id: 'readme',
    label: 'Project README',
    stage: 'DOCS',
    role: 'Documenter',
    path: 'README.md',
    icon: BookOpen,
  },
];

export const ArtifactsView: React.FC<ArtifactsViewProps> = ({ runId }) => {
  const [selectedId, setSelectedId] = useState<string>('requirements');
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [viewRaw, setViewRaw] = useState<boolean>(false);

  const selectedArtifact =
    DEFAULT_ARTIFACTS.find((a) => a.id === selectedId) || DEFAULT_ARTIFACTS[0];

  useEffect(() => {
    if (!runId || !selectedArtifact) return;
    setLoading(true);
    fetchFileContent(runId, selectedArtifact.path)
      .then((res) => {
        setContent(res.content || '');
      })
      .catch(() => {
        setContent(`*(Artifact '${selectedArtifact.path}' is not yet created for this run)*`);
      })
      .finally(() => setLoading(false));
  }, [runId, selectedArtifact]);

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = selectedArtifact.path.split('/').pop() || 'artifact.md';
    link.click();
    URL.revokeObjectURL(url);
  };

  /**
   * Render markdown with special handling for Mermaid blocks, headers, tables, lists
   */
  const renderMarkdown = (text: string) => {
    const lines = text.split('\n');
    const elements: React.ReactNode[] = [];
    let inCodeBlock = false;
    let codeLanguage = '';
    let codeLines: string[] = [];
    let inTable = false;
    let tableRows: string[][] = [];

    const flushTable = (key: number) => {
      if (tableRows.length === 0) return null;
      const [header, , ...body] = tableRows;
      const res = (
        <div key={`table-${key}`} className="my-4 overflow-x-auto">
          <table className="min-w-full text-xs text-left border border-gray-800 divide-y divide-gray-800">
            {header && (
              <thead className="bg-gray-900/80 text-gray-300 font-semibold uppercase tracking-wider">
                <tr>
                  {header.map((col, cIdx) => (
                    <th key={cIdx} className="px-3 py-2 border-r border-gray-800 last:border-0">
                      {col.trim()}
                    </th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody className="divide-y divide-gray-800/60 bg-gray-950/40">
              {body.map((row, rIdx) => (
                <tr key={rIdx} className="hover:bg-gray-900/40 transition-colors">
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} className="px-3 py-2 border-r border-gray-800/60 last:border-0 text-gray-300">
                      {cell.trim()}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      tableRows = [];
      inTable = false;
      return res;
    };

    lines.forEach((line, index) => {
      // Code blocks
      if (line.startsWith('```')) {
        if (!inCodeBlock) {
          if (inTable) elements.push(flushTable(index));
          inCodeBlock = true;
          codeLanguage = line.slice(3).trim();
          codeLines = [];
        } else {
          inCodeBlock = false;
          const codeString = codeLines.join('\n');
          if (codeLanguage === 'mermaid') {
            elements.push(
              <div
                key={`mermaid-${index}`}
                className="my-4 p-4 rounded-xl bg-gradient-to-br from-indigo-950/40 via-gray-950 to-gray-900 border border-indigo-700/40 shadow-lg"
              >
                <div className="flex items-center justify-between pb-2 mb-2 border-b border-indigo-800/40">
                  <span className="text-xs font-bold text-indigo-400 flex items-center gap-1.5 uppercase tracking-wider">
                    <Compass className="w-4 h-4" /> Mermaid Architecture Diagram
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-900/60 text-indigo-300 border border-indigo-700/50">
                    System Diagram
                  </span>
                </div>
                <pre className="text-xs font-mono text-cyan-300 bg-gray-950/90 p-3 rounded-lg overflow-x-auto whitespace-pre">
                  {codeString}
                </pre>
              </div>
            );
          } else {
            elements.push(
              <div key={`code-${index}`} className="my-3 rounded-lg border border-gray-800 overflow-hidden font-mono text-xs">
                {codeLanguage && (
                  <div className="px-3 py-1 bg-gray-900 text-[10px] text-gray-400 uppercase font-semibold border-b border-gray-800">
                    {codeLanguage}
                  </div>
                )}
                <pre className="p-3 bg-gray-950 text-gray-300 overflow-x-auto whitespace-pre">
                  {codeString}
                </pre>
              </div>
            );
          }
        }
        return;
      }

      if (inCodeBlock) {
        codeLines.push(line);
        return;
      }

      // Tables
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        inTable = true;
        const cells = line.split('|').slice(1, -1);
        tableRows.push(cells);
        return;
      } else if (inTable) {
        elements.push(flushTable(index));
      }

      // Headings
      if (line.startsWith('# ')) {
        elements.push(
          <h1 key={index} className="text-xl font-extrabold text-white mt-6 mb-3 pb-2 border-b border-gray-800">
            {line.slice(2)}
          </h1>
        );
        return;
      }
      if (line.startsWith('## ')) {
        elements.push(
          <h2 key={index} className="text-base font-bold text-indigo-300 mt-5 mb-2">
            {line.slice(3)}
          </h2>
        );
        return;
      }
      if (line.startsWith('### ')) {
        elements.push(
          <h3 key={index} className="text-sm font-semibold text-gray-200 mt-4 mb-2">
            {line.slice(4)}
          </h3>
        );
        return;
      }

      // Blockquotes
      if (line.startsWith('> ')) {
        elements.push(
          <blockquote
            key={index}
            className="my-2 border-l-4 border-indigo-500 pl-3 py-1 text-xs text-indigo-200/90 italic bg-indigo-950/20 rounded-r"
          >
            {line.slice(2)}
          </blockquote>
        );
        return;
      }

      // Bullet lists
      if (line.startsWith('- ') || line.startsWith('* ')) {
        elements.push(
          <div key={index} className="flex items-start gap-2 text-xs text-gray-300 my-1 ml-2">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 shrink-0" />
            <span>{line.slice(2)}</span>
          </div>
        );
        return;
      }

      // Empty lines
      if (!line.trim()) {
        elements.push(<div key={index} className="h-2" />);
        return;
      }

      // Regular paragraph
      elements.push(
        <p key={index} className="text-xs text-gray-300 leading-relaxed my-1.5">
          {line}
        </p>
      );
    });

    if (inTable) {
      elements.push(flushTable(lines.length));
    }

    return elements;
  };

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-5 shadow-xl backdrop-blur-sm">
      <div className="flex flex-col md:flex-row gap-5">
        {/* Left Sidebar: Artifact Selector */}
        <div className="w-full md:w-64 shrink-0 space-y-2">
          <div className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2 flex items-center gap-1.5">
            <FileBox className="w-4 h-4 text-indigo-400" />
            <span>Stage Deliverables</span>
          </div>

          <div className="space-y-1.5">
            {DEFAULT_ARTIFACTS.map((artifact) => {
              const Icon = artifact.icon;
              const isSelected = selectedId === artifact.id;
              return (
                <button
                  key={artifact.id}
                  onClick={() => setSelectedId(artifact.id)}
                  className={`w-full text-left p-3 rounded-lg border transition-all flex items-center gap-3 ${
                    isSelected
                      ? 'border-indigo-500 bg-indigo-950/40 text-white shadow-lg shadow-indigo-500/10'
                      : 'border-gray-800/80 bg-gray-950/50 text-gray-400 hover:border-gray-700 hover:text-gray-200'
                  }`}
                >
                  <div
                    className={`w-8 h-8 rounded-md flex items-center justify-center shrink-0 ${
                      isSelected
                        ? 'bg-indigo-600 text-white'
                        : 'bg-gray-900 text-gray-400 border border-gray-800'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-bold truncate">
                      {artifact.label}
                    </div>
                    <div className="text-[10px] text-gray-500 font-mono truncate">
                      {artifact.role} • {artifact.stage}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right Main Content: Document Viewer */}
        <div className="flex-1 min-w-0 bg-gray-950 border border-gray-800 rounded-lg p-5 flex flex-col">
          {/* Action Header */}
          <div className="flex items-center justify-between pb-3 border-b border-gray-800 mb-4 flex-wrap gap-2">
            <div>
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                <span>{selectedArtifact.label}</span>
                <span className="text-[10px] font-mono text-gray-400 px-2 py-0.5 rounded bg-gray-900 border border-gray-800">
                  {selectedArtifact.path}
                </span>
              </h2>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setViewRaw(!viewRaw)}
                className={`px-2.5 py-1 rounded text-xs font-medium border flex items-center gap-1.5 transition-colors ${
                  viewRaw
                    ? 'bg-indigo-600 text-white border-indigo-500'
                    : 'bg-gray-900 text-gray-400 border-gray-800 hover:text-white'
                }`}
              >
                {viewRaw ? <Eye className="w-3.5 h-3.5" /> : <Code2 className="w-3.5 h-3.5" />}
                <span>{viewRaw ? 'Rendered' : 'Raw Markdown'}</span>
              </button>

              <button
                onClick={handleCopy}
                className="px-2.5 py-1 rounded text-xs font-medium bg-gray-900 text-gray-400 border border-gray-800 hover:text-white hover:border-gray-700 flex items-center gap-1.5 transition-colors"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>

              <button
                onClick={handleDownload}
                className="px-2.5 py-1 rounded text-xs font-medium bg-gray-900 text-gray-400 border border-gray-800 hover:text-white hover:border-gray-700 flex items-center gap-1.5 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Save</span>
              </button>
            </div>
          </div>

          {/* Document Content */}
          <div className="flex-1 overflow-y-auto max-h-[600px] pr-2">
            {loading ? (
              <div className="text-center py-16 text-xs text-gray-500 animate-pulse">
                Loading artifact content...
              </div>
            ) : viewRaw ? (
              <pre className="font-mono text-xs text-gray-300 whitespace-pre-wrap p-3 bg-black/40 rounded-lg border border-gray-900">
                {content}
              </pre>
            ) : (
              <div className="prose prose-invert max-w-none text-xs">
                {renderMarkdown(content)}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
