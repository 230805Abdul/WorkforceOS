/** Small label shown on records that came from the seed script (is_sample = true in the database). */
export default function SampleTag({ show }) {
  if (!show) return null;
  return <span className="sample-tag" title="Inserted by the sample-data script">Sample</span>;
}
