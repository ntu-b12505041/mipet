"""Generate an ArUco marker image for the stop sign."""

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a MiPet ArUco stop marker")
    parser.add_argument("--id", type=int, default=0, help="Marker ID. Default: 0")
    parser.add_argument("--size", type=int, default=600, help="Image size in pixels.")
    parser.add_argument("--dictionary", default="DICT_4X4_50", help="OpenCV ArUco dictionary name.")
    parser.add_argument("--output", default="aruco_0.png", help="Output PNG path.")
    args = parser.parse_args()

    import cv2

    aruco = cv2.aruco
    dictionary_id = getattr(aruco, args.dictionary)
    if hasattr(aruco, "getPredefinedDictionary"):
        dictionary = aruco.getPredefinedDictionary(dictionary_id)
    else:
        dictionary = aruco.Dictionary_get(dictionary_id)

    if hasattr(aruco, "generateImageMarker"):
        image = aruco.generateImageMarker(dictionary, args.id, args.size)
    else:
        image = aruco.drawMarker(dictionary, args.id, args.size)

    cv2.imwrite(args.output, image)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
