export default function EditorToolbar({ canUndo, canRedo, onUndo, onRedo, onSave, onExport }) {
  return (
    <div className="editor-topbar-actions">
      <button type="button" className="editor-btn" disabled={!canUndo} onClick={onUndo}>↶</button>
      <button type="button" className="editor-btn" disabled={!canRedo} onClick={onRedo}>↷</button>
      <button type="button" className="editor-btn" onClick={onSave}>Save</button>
      <button type="button" className="editor-btn editor-btn-primary" onClick={onExport}>Export</button>
    </div>
  )
}
