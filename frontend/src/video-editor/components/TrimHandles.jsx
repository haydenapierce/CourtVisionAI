export default function TrimHandles({ onTrimStart }) {
  return (
    <>
      <button
        type="button"
        className="nle-trim-handle left"
        aria-label="Trim clip start"
        onPointerDown={(event) => onTrimStart?.(event, "left")}
        onClick={(event) => event.stopPropagation()}
      />
      <button
        type="button"
        className="nle-trim-handle right"
        aria-label="Trim clip end"
        onPointerDown={(event) => onTrimStart?.(event, "right")}
        onClick={(event) => event.stopPropagation()}
      />
    </>
  )
}
