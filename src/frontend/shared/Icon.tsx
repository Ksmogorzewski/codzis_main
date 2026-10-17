// Ikona Material Symbols (font ładowany w index.html; wariant Rounded/Outlined wybiera CSS aplikacji)
type Props = { name: string; fill?: boolean; size?: number; className?: string };

export function Icon({ name, fill, size, className }: Props) {
  const classes = ["ms", fill ? "ms-fill" : "", className ?? ""].filter(Boolean).join(" ");
  return (
    <span className={classes} style={size ? { fontSize: size } : undefined} aria-hidden="true">
      {name}
    </span>
  );
}
