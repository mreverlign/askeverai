import Image from "next/image";

export type EverlignLogoVariant = "mark" | "lockup";

export interface EverlignLogoProps {
  variant?: EverlignLogoVariant;
  alt?: string;
  decorative?: boolean;
  className?: string;
  priority?: boolean;
  sizes?: string;
}

const LOGO_ASSETS = {
  mark: {
    src: "/brand/everlign-mark.svg",
    width: 40,
    height: 40,
  },
  lockup: {
    src: "/brand/everlign-logo.svg",
    width: 162,
    height: 40,
  },
} as const;

export function EverlignLogo({
  variant = "lockup",
  alt = "Everlign",
  decorative = false,
  className,
  priority = false,
  sizes,
}: EverlignLogoProps) {
  const asset = LOGO_ASSETS[variant];

  return (
    <Image
      src={asset.src}
      width={asset.width}
      height={asset.height}
      alt={decorative ? "" : alt}
      aria-hidden={decorative || undefined}
      className={className}
      priority={priority}
      sizes={sizes}
      draggable={false}
      unoptimized
    />
  );
}
