import os, glob, subprocess, zipfile, shutil

JAVA_HOME = r'C:\Program Files\Java\jdk1.8.0_341'
JAVAC = os.path.join(JAVA_HOME, 'bin', 'javac.exe')
JAVA = os.path.join(JAVA_HOME, 'bin', 'java.exe')
JARSIGNER = os.path.join(JAVA_HOME, 'bin', 'jarsigner.exe')

# 1. compile java
classes_dir = r'MixMonolithBuild\build\classes'
os.makedirs(classes_dir, exist_ok=True)
for f in glob.glob(os.path.join(classes_dir, '*')):
    if os.path.isfile(f): os.remove(f)

src_files = glob.glob(r'MixMonolithBuild\src\com\mix\monolith\*.java')
cmd_javac = [JAVAC, '-cp', 'android.jar;jsch.jar', '-d', classes_dir] + src_files
print('Compiling:', cmd_javac)
subprocess.check_call(cmd_javac)

# 2. dex with r8
dex_dir = r'MixMonolithBuild\build\dex'
os.makedirs(dex_dir, exist_ok=True)
classes = glob.glob(r'MixMonolithBuild\build\classes\com\mix\monolith\*.class')
cmd_dex = [JAVA, '-cp', 'r8.jar', 'com.android.tools.r8.D8', '--output', dex_dir] + classes + ['jsch.jar']
print('Dexing:', cmd_dex)
subprocess.check_call(cmd_dex)

# 3. link resources with aapt2
cmd_aapt2 = [
    r'.\aapt2.exe', 'link',
    '-I', 'android.jar',
    r'MixMonolithBuild\build\resources.zip',
    '--manifest', r'MixMonolithBuild\AndroidManifest.xml',
    '-A', r'MixMonolithBuild\assets',
    '-o', r'MixMonolithBuild\build\unaligned.apk',
    '--java', r'MixMonolithBuild\build\gen',
    '--auto-add-overlay'
]
print('Aapt2 link...')
subprocess.check_call(cmd_aapt2)

# 4. inject classes.dex into unaligned.apk
print('Adding dex to unaligned.apk...')
with zipfile.ZipFile(r'MixMonolithBuild\build\unaligned.apk', 'a') as z:
    z.write(r'MixMonolithBuild\build\dex\classes.dex', 'classes.dex')

shutil.copyfile(r'MixMonolithBuild\build\unaligned.apk', 'MixMonolith_v1.0.apk')

# 5. sign with jarsigner
cmd_sign = [
    JARSIGNER,
    '-keystore', 'debug.keystore',
    '-storepass', 'android',
    '-keypass', 'android',
    'MixMonolith_v1.0.apk',
    'androiddebugkey'
]
print('Signing APK...')
subprocess.check_call(cmd_sign)

# 6. install and launch
print('Installing via adb...')
subprocess.check_call(['adb', 'install', '-r', 'MixMonolith_v1.0.apk'])
print('Stopping old instance...')
subprocess.run(['adb', 'shell', 'am', 'force-stop', 'com.mix.monolith'])
print('Launching new instance...')
subprocess.check_call(['adb', 'shell', 'am', 'start', '-n', 'com.mix.monolith/.MainActivity'])
print('SUCCESS!')
