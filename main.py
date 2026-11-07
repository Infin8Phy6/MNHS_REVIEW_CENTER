# MNHS Review Center - ESP32 access point + captive portal (MicroPython)
# Save on the board as main.py, then Ctrl+D to soft reboot.
#
# Students join MNHS-Review. Anything they open is answered by the board and
# sent to the Flask app on the laptop, so nobody types an address.
#
# The laptop joins MNHS-Review as an ordinary client (DHCP, no static IP).
# The board finds it by probing port 5000 on its own clients and remembers it.
# To sync results, switch the laptop back to the Globe router; the board does
# not route between the two networks.

import gc
import machine
import network
import select
import socket
import time

SSID = "MNHS-Review"
PASSWORD = "review2026"          # WPA2 needs 8-63 characters
CHANNEL = 1                      # the Globe router sits on channel 8
MAX_CLIENTS = 10                 # ESP32 firmware caps this at 10, laptop included
AP_IP = "192.168.4.1"
APP_HOST = None                  # "192.168.4.50" to skip auto-discovery
APP_PORT = 5000
PORTAL = True                    # False = plain AP, students type the address

DISCOVER_FIRST = 2               # probe 192.168.4.2 ... 192.168.4.30
DISCOVER_LAST = 30
DISCOVER_EVERY_MS = 10000
PROBE_TIMEOUT = 0.15
CLIENT_PRINT_MS = 5000
GC_EVERY_MS = 30000

PREFIX = AP_IP.rsplit(".", 1)[0]
AP_BYTES = bytes([int(part) for part in AP_IP.split(".")])
found_host = APP_HOST

WAITING_PAGE = (
    '<!doctype html><meta charset="utf-8"><title>MNHS Review Center</title>'
    '<meta http-equiv="refresh" content="3;url=http://{0}/">'
    '<body style="font-family:sans-serif;text-align:center;padding:48px">'
    '<h2>MNHS Review Center</h2>'
    '<p>Looking for the review laptop&hellip;</p>'
    '<p>Keep this page open &mdash; it opens the quiz by itself.</p>'
    '<p><a href="http://{0}/">{0}</a></p>'
).format(AP_IP).encode()


def start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=SSID, password=PASSWORD,
              authmode=network.AUTH_WPA2_PSK, channel=CHANNEL)
    try:
        ap.config(max_clients=MAX_CLIENTS)
    except (ValueError, TypeError):
        print("this firmware has no max_clients option; default limit applies")
    ap.ifconfig((AP_IP, "255.255.255.0", AP_IP, AP_IP))
    return ap


def probe(ip):
    sock = socket.socket()
    try:
        sock.settimeout(PROBE_TIMEOUT)
        sock.connect((ip, APP_PORT))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def discover():
    gc.collect()
    for last in range(DISCOVER_FIRST, DISCOVER_LAST + 1):
        ip = "%s.%d" % (PREFIX, last)
        if probe(ip):
            return ip
    return None


def app_url():
    if found_host:
        return "http://%s:%d/" % (found_host, APP_PORT)
    return None


def dns_reply(query):
    if len(query) < 17:
        return None
    i = 12
    while i < len(query) and query[i]:
        if query[i] & 0xC0:
            return None
        i += query[i] + 1
    if i + 5 > len(query):
        return None
    qtype = (query[i + 1] << 8) | query[i + 2]
    question = query[12:i + 5]
    if qtype == 1:
        header = query[:2] + b"\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00"
        answer = (b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04"
                  + AP_BYTES)
    else:
        header = query[:2] + b"\x81\x80\x00\x01\x00\x00\x00\x00\x00\x00"
        answer = b""
    return header + question + answer


def answer_dns(sock):
    try:
        query, sender = sock.recvfrom(512)
    except OSError:
        return
    reply = dns_reply(query)
    if reply is None:
        return
    try:
        sock.sendto(reply, sender)
    except OSError:
        pass


def http_response():
    target = app_url()
    if target:
        return (b"HTTP/1.1 302 Found\r\nLocation: " + target.encode()
                + b"\r\nCache-Control: no-store\r\nContent-Length: 0\r\n"
                  b"Connection: close\r\n\r\n")
    return (b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
            b"Cache-Control: no-store\r\nConnection: close\r\nContent-Length: "
            + str(len(WAITING_PAGE)).encode() + b"\r\n\r\n" + WAITING_PAGE)


def answer_http(sock):
    try:
        client, _ = sock.accept()
    except OSError:
        return
    try:
        client.settimeout(0.4)
        try:
            client.recv(1024)
        except OSError:
            pass
        client.sendall(http_response())
    except OSError:
        pass
    finally:
        client.close()


def make_udp(port):
    for _attempt in range(5):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("0.0.0.0", port))
            sock.setblocking(False)
            return sock
        except OSError:
            sock.close()
            time.sleep(1)
    raise OSError("port %d is still busy - reset the board" % port)


def make_tcp(port):
    for _attempt in range(5):
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
            sock.listen(4)
            sock.setblocking(False)
            return sock
        except OSError:
            sock.close()
            time.sleep(1)
    raise OSError("port %d is still busy - reset the board" % port)


def main():
    global found_host

    auto_host = not APP_HOST
    ap = start_ap()
    print("")
    print("MNHS Review Center - ESP32 portal")
    print("SSID:    ", SSID)
    print("Password:", PASSWORD)
    print("AP IP:   ", ap.ifconfig()[0])
    print("Phones:   open any page; the portal forwards them")
    print("Laptop:   join %s, then run start_local.bat" % SSID)
    if found_host:
        print("App:     ", app_url())
    else:
        print("App:      http://%s.x:%d (found automatically)" % (PREFIX, APP_PORT))

    if PORTAL:
        dns_sock = make_udp(53)
        http_sock = make_tcp(80)
        poller = select.poll()
        poller.register(dns_sock, select.POLLIN)
        poller.register(http_sock, select.POLLIN)
    else:
        dns_sock = http_sock = poller = None

    now = time.ticks_ms()
    last_print = time.ticks_add(now, -CLIENT_PRINT_MS)
    last_gc = now
    next_probe = now
    last_count = -1
    warned = False

    while True:
        if PORTAL:
            for ready, _event in poller.poll(1000):
                if ready is dns_sock:
                    answer_dns(dns_sock)
                elif ready is http_sock:
                    answer_http(http_sock)
        else:
            time.sleep(1)

        now = time.ticks_ms()
        try:
            count = len(ap.status("stations") or [])
        except Exception:
            count = 0

        if count != last_count:
            previous = last_count
            last_count = count
            warned = False
            if not count and auto_host:
                found_host = None
                next_probe = now
            elif count > previous and not found_host:
                next_probe = now
            elif count < previous and auto_host and found_host and not probe(found_host):
                print("app host", found_host, "is gone; searching again")
                found_host = None
                next_probe = now

        if time.ticks_diff(now, last_print) >= CLIENT_PRINT_MS:
            last_print = now
            print("clients:", count, "| app:", app_url() or "searching")

        if PORTAL and not found_host and count and time.ticks_diff(now, next_probe) >= 0:
            next_probe = time.ticks_add(now, DISCOVER_EVERY_MS)
            host = discover()
            if host:
                found_host = host
                print("app found at", app_url())
            elif not warned:
                warned = True
                print("no app yet on %s.2-%d:%d - is start_local.bat running?"
                      % (PREFIX, DISCOVER_LAST, APP_PORT))

        if time.ticks_diff(now, last_gc) >= GC_EVERY_MS:
            last_gc = now
            gc.collect()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("stopped")
    except Exception as error:
        print("FATAL:", error)
        time.sleep(5)
        machine.reset()
