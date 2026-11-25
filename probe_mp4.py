"""极简 MP4 探测：不依赖 ffmpeg，读 moov/mvhd 拿时长与轨道数。"""
import struct
import sys


def boxes(data, start, end):
    pos = start
    while pos + 8 <= end:
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8].decode("latin-1")
        header = 8
        if size == 1:
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        yield typ, pos + header, pos + size
        pos += size


def find(data, path, start=0, end=None):
    end = len(data) if end is None else end
    for typ, s, e in boxes(data, start, end):
        if typ == path[0]:
            if len(path) == 1:
                return s, e
            return find(data, path[1:], s, e)
    return None


def main(path):
    data = open(path, "rb").read()
    moov = find(data, ["moov"])
    if not moov:
        print("no moov")
        return
    mvhd = find(data, ["mvhd"], *moov)
    if mvhd:
        s, _ = mvhd
        version = data[s]
        if version == 1:
            timescale = struct.unpack(">I", data[s + 20:s + 24])[0]
            duration = struct.unpack(">Q", data[s + 24:s + 32])[0]
        else:
            timescale = struct.unpack(">I", data[s + 12:s + 16])[0]
            duration = struct.unpack(">I", data[s + 16:s + 20])[0]
        print(f"duration={duration / timescale:.1f}s timescale={timescale}")

    tracks = []
    for typ, s, e in boxes(data, *moov):
        if typ == "trak":
            hdlr = find(data, ["mdia", "hdlr"], s, e)
            kind = "?"
            if hdlr:
                kind = data[hdlr[0] + 8:hdlr[0] + 12].decode("latin-1")
            tracks.append(kind)
    print("tracks:", tracks)
    print("size_MB:", round(len(data) / 1024 / 1024, 2))


if __name__ == "__main__":
    main(sys.argv[1])
