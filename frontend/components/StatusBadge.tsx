export function StatusBadge({ available }: { available: boolean | null | undefined }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${
        available === true
          ? "bg-green-400"
          : available === false
          ? "bg-red-400"
          : "bg-yellow-400"
      }`}
    />
  );
}
