"""IntruShield - shared configuration: paths, column names, attack taxonomy."""
from pathlib import Path

RANDOM_STATE = 42
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
CANDIDATES_DIR = MODELS_DIR / "candidates"
REPORTS_DIR = ROOT / "reports"
FIG_DIR = REPORTS_DIR / "figures"
for d in (DATA_DIR, MODELS_DIR, CANDIDATES_DIR, REPORTS_DIR, FIG_DIR):
    d.mkdir(parents=True, exist_ok=True)

RAW_BASE = "https://raw.githubusercontent.com/jmnwong/NSL-KDD-Dataset/master/"
FILES = {"train": "KDDTrain+.txt", "test": "KDDTest+.txt", "test21": "KDDTest-21.txt"}

COLUMNS = [
    "duration", "protocol_type", "service", "flag", "src_bytes", "dst_bytes", "land",
    "wrong_fragment", "urgent", "hot", "num_failed_logins", "logged_in", "num_compromised",
    "root_shell", "su_attempted", "num_root", "num_file_creations", "num_shells",
    "num_access_files", "num_outbound_cmds", "is_host_login", "is_guest_login", "count",
    "srv_count", "serror_rate", "srv_serror_rate", "rerror_rate", "srv_rerror_rate",
    "same_srv_rate", "diff_srv_rate", "srv_diff_host_rate", "dst_host_count",
    "dst_host_srv_count", "dst_host_same_srv_rate", "dst_host_diff_srv_rate",
    "dst_host_same_src_port_rate", "dst_host_srv_diff_host_rate", "dst_host_serror_rate",
    "dst_host_srv_serror_rate", "dst_host_rerror_rate", "dst_host_srv_rerror_rate",
    "attack", "difficulty",
]
FEATURES = COLUMNS[:41]
CATEGORICAL = ["protocol_type", "service", "flag"]
NUMERIC = [c for c in FEATURES if c not in CATEGORICAL]
# Heavily right-skewed byte / count columns -> log1p
SKEWED = [
    "duration", "src_bytes", "dst_bytes", "hot", "num_failed_logins", "num_compromised",
    "num_root", "num_file_creations", "num_shells", "num_access_files", "count", "srv_count",
    "dst_host_count", "dst_host_srv_count", "wrong_fragment", "urgent",
]

ATTACK_MAP = {
    "DoS": ["back", "land", "neptune", "pod", "smurf", "teardrop", "apache2", "mailbomb",
            "processtable", "udpstorm"],
    "Probe": ["ipsweep", "nmap", "portsweep", "satan", "mscan", "saint"],
    "R2L": ["ftp_write", "guess_passwd", "imap", "multihop", "phf", "spy", "warezclient",
            "warezmaster", "named", "sendmail", "snmpgetattack", "snmpguess", "xlock", "xsnoop",
            "worm"],
    "U2R": ["buffer_overflow", "loadmodule", "perl", "rootkit", "httptunnel", "ps", "sqlattack",
            "xterm"],
    "Normal": ["normal"],
}
LABEL_TO_CLASS = {a: c for c, lst in ATTACK_MAP.items() for a in lst}
CLASSES = ["Normal", "DoS", "Probe", "R2L", "U2R"]

NAVY, TEAL = "#0b2545", "#13a4a4"
PALETTE = ["#2a5ea8", "#0a9c9c", "#d9781c", "#7a5cc7", "#b83a3a"]  # CVD-validated
