# 👶 GridMind: Complete Baby-Steps Connection Guide

Welcome! This guide explains exactly what the **Master Laptop** needs to do and what the **Worker Laptops (Teammates)** need to do to get the GridMind cluster running.

---

## 📱 Step 1: The Network (Everyone Does This)
Since we don't have a regular Wi-Fi network, we need to create our own mini-network using a Mobile Hotspot.
1. **The Master Laptop owner** must turn on their phone's Mobile Hotspot.
2. **Every other teammate** must click their Wi-Fi menu and connect their laptops to that exact same Mobile Hotspot.
*(⚠️ If you skip this step, nobody will be able to talk to the Master laptop!)*

---

## 👑 SECTION A: For the Master Laptop ONLY
*The Master Laptop controls the central server and the dashboard.*

### Step 1: Open Your Terminal
- **Windows:** Press the `Windows` key, type `cmd`, and press Enter.
- **Mac:** Press `Cmd + Space`, type `Terminal`, and press Enter.

### Step 2: Start GridMind
Assuming you already have the code downloaded and your Python environment set up, go to the project folder and start the whole system:
```bash
python start_gridmind.py
```

### Step 3: Write Down the Master IP
When the server starts, it will print a cool text graphic. Look for the line that says:
`📍 Master Node IP: <SOME_NUMBERS>`
*(Example: `192.168.43.5` or `172.20.10.4`)*
**Write this number down or text it to your teammates.** They need it for their next step!

### Step 4: Windows Firewall (Crucial!)
If your teammates run into connection errors, it is almost definitely Windows blocking them.
1. Open the Start Menu and search for **"Windows Defender Firewall"**.
2. Click **"Turn Windows Defender Firewall on or off"** on the left menu.
3. Temporarily turn it **Off** for the "Private Network" while running GridMind.

---

## 💻 SECTION B: For the Worker Nodes (Teammates)
*Your laptops will do the actual computing work in the background.*

### Step 1: Open Your Terminal
- **Windows:** Press the `Windows` key, type `cmd`, and press Enter.
- **Mac:** Press `Cmd + Space`, type `Terminal`, and press Enter.

### Step 2: Download the Code
Copy and paste this command and hit Enter:
```bash
git clone <your-repo-url>
```
*(Ask your team for the exact `<your-repo-url>`!)*

Once it finishes, jump into the folder:
```bash
cd Mini_Project
```

### Step 3: Create & Activate a "Virtual Environment"
A virtual environment keeps things organized. Type this to create it:
```bash
python -m venv .venv
```
Now, **turn it on**:
- **Windows:** `.venv\Scripts\activate`
- **Mac/Linux:** `source .venv/bin/activate`
*(You should see `(.venv)` appear on your screen!)*

### Step 4: Install Required Packages
Install the tools GridMind needs by typing:
```bash
pip install -r requirements.txt
```
*(Wait until all the loading bars finish and it gives you a fresh typing line.)*

### Step 5: Start Your Agent and Connect!
Ask the Master Laptop for the IP address they got in **Section A, Step 3**. 

Type this command, replacing `<MASTER_IP>` with their numbers, and `<YOUR_NAME>` with your name (no spaces):
```bash
python gridmind_node/agent.py --server <MASTER_IP>:50051 --node-id <YOUR_NAME>
```

**Example:** If the master IP is `192.168.43.5` and your name is `Alex`:
```bash
python gridmind_node/agent.py --server 192.168.43.5:50051 --node-id Alex
```

### 🎉 How to Know if it Worked!
Look at your terminal window. If it prints:
`Connected to GridMind server at...`
**Congratulations!** Leave this terminal running in the background. 

To see your laptop's stats, go to your web browser and visit `http://<MASTER_IP>:3005`. You will see a neat dashboard showing your name!

---

## 🚨 Troubleshooting
If you see a **gRPC Error** (like `_MultiThreadedRendezvous`):
Your laptop is trying to talk, but the Master laptop is ignoring it.

**Fix 1: Change Master Laptop's Wi-Fi to "Private"**
If the Master laptop is Windows, it defaults to hiding itself on new networks.
1. On the **Master Laptop**, click the Wi-Fi icon.
2. Click the `i` (Info/Properties) button next to your connected Hotspot.
3. Change the Network Profile type from **Public** to **Private**.

**Fix 2: Type the Port Number!**
Make absolutely sure you added `:50051` to the end of the IP address when typing the command! (Example: `192.168.43.5:50051`)

**Fix 3: Firewall Block**
If changing to Private doesn't work, the Master Laptop's Windows Firewall is blocking Python. When starting the server initially, Windows usually pops up asking "Windows Defender Firewall has blocked some features of this app". The Master MUST click **Allow Access**.

---

## 🛑 Troubleshooting Common Errors

### Error: `tcp handshaker shutdown` or `failed to connect to all addresses`
- **Cause:** You are either using the wrong Master IP address, or the Master Laptop's firewall is blocking you.
- **Fix:** Double-check the Master IP address with the host. If it's perfectly correct, ask the Master Laptop owner to complete **Section A, Step 4** (Turn off Windows Firewall for Private Networks).

### Error: `'next' is not recognized` 
- **Cause:** You are trying to run the web dashboard on your laptop.
- **Fix:** Stop! Only the Master Laptop runs the dashboard. Worker laptops only need to run the Python agent command.

### Error: `Connection refused ... ipv4:127.0.0.1:50051`
- **Cause:** You forgot to add `--server <MASTER_IP>:50051` to your command, so your laptop is trying to connect to a server on itself (`127.0.0.1`).
- **Fix:** Run the full command exactly as shown in **Step 5**, making sure to include the Master's IP!
