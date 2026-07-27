export default function ClipContextMenu({ visible, x = 0, y = 0, onSplit, onDuplicate, onRemove }) {
  if (!visible) return null
  return (
    <div className="clip-context-menu" style={{ left: x, top: y }}>
      <button type="button" onClick={onSplit}>Split</button>
      <button type="button" onClick={onDuplicate}>Duplicate</button>
      <button type="button" onClick={onRemove}>Remove</button>
    </div>
  )
}
