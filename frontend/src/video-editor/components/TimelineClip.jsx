export default function TimelineClip({ selected, width, children, ...props }) {
  return (
    <article
      className={`nle-clip ${selected ? "selected" : ""}`}
      style={{ width, minWidth: width, flexBasis: width }}
      {...props}
    >
      {children}
    </article>
  )
}
