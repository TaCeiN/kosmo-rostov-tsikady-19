import os
import glob
import struct
import subprocess

TARGET_DIR = "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages"

def patch_macho_file(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
            if magic not in (b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"):
                return False
            f.seek(0)
            content = bytearray(f.read())

        magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack_from("<8I", content, 0)
        pos = 32
        modified = False

        for _ in range(ncmds):
            cmd, cmdsize = struct.unpack_from("<2I", content, pos)
            if cmd == 0x19:  # LC_SEGMENT_64
                nsects = struct.unpack_from("<I", content, pos + 64)[0]
                spos = pos + 72
                for _s in range(nsects):
                    sectname = content[spos:spos + 16].rstrip(b"\x00").decode("latin1", errors="ignore")
                    off, align, reloff, nreloc, s_flags = struct.unpack_from("<5I", content, spos + 48)
                    s_type = s_flags & 0xff
                    # S_ZEROFILL (1) or S_THREAD_LOCAL_ZEROFILL (0x12 = 18)
                    if s_type in (1, 0x12) and off != 0:
                        print(f"[{os.path.basename(path)}] Patching {sectname}: offset {off} -> 0")
                        struct.pack_into("<I", content, spos + 48, 0)
                        modified = True
                    spos += 80
            pos += cmdsize

        if modified:
            with open(path, "wb") as f:
                f.write(content)
            res = subprocess.run(["codesign", "-s", "-", "-f", path], capture_output=True, text=True)
            if res.returncode != 0:
                print(f"Warning: codesign failed for {path}: {res.stderr}")
            else:
                print(f"Successfully resigned {os.path.basename(path)}")
            return True
    except Exception as e:
        print(f"Error processing {path}: {e}")
    return False

def main():
    count = 0
    pattern = os.path.join(TARGET_DIR, "**/*.so")
    print(f"Scanning {TARGET_DIR} for Mach-O binaries with non-zero zero-fill offsets...")
    for p in glob.glob(pattern, recursive=True):
        if patch_macho_file(p):
            count += 1
    print(f"\nFinished! Patched and resigned {count} libraries.\n")

if __name__ == "__main__":
    main()
