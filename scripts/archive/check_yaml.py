from pathlib import Path
p=Path(r'c:\Projects\epycon\.github\workflows\windows-build-release.yml')
b=p.read_bytes()
print('First 100 bytes repr:', repr(b[:100]))
print('Contains BOM (utf-8 sig):', b.startswith(b'\xef\xbb\xbf'))
text=b.decode('utf-8')
tabs=[i+1 for i,l in enumerate(text.splitlines()) if '\t' in l]
print('Tabs at lines:', tabs)
print('\nFile preview:')
for i,line in enumerate(text.splitlines(),1):
    print(f'{i:3}: {line}')
