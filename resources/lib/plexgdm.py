"""
PlexGDM.py - Version 0.1

This class implements the Plex GDM (G'Day Mate) protocol to discover
local Plex Media Servers.  Also allow client registration into all local
media servers.


This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
MA 02110-1301, USA.
"""

__author__ = 'DHJ (hippojay) <plex@h-jay.com>'

import socket
import struct
import sys
import re
import threading
import time
import urllib2

class plexgdm:

    def __init__(self, debug=0):
        
        self.discover_message = 'M-SEARCH * HTTP/1.1'
        self.client_register_header = 'HELLO * HTTP/1.1'
        self.client_deregister_header = 'BYE * HTTP/1.1'
        self.client_data = None
        self.client_id = None
        
        self._multicast_address = '239.0.0.250'
        self.discover_group = (self._multicast_address, 32414)
        self.client_register_group = (self._multicast_address, 32413)

        self.server_list = []
        self.discovery_interval = 120
        self.client_interval = 5
        
        self._discovery_is_running = False
        self._registration_is_running = False

        self.discovery_complete = False
        self.client_registered = False
        self.debug = debug

    def __printDebug(self, message, level=1):
        if self.debug >= level:
            print "PlexGDM: %s" % message

    def clientDetails(self, c_id, c_name, c_post, c_product, c_version):
        self.client_data = "Content-Type: plex/media-player\nResource-Identifier: %s\nName: %s\nPort: %s\nProduct: %s\nVersion: %s" % ( c_id, c_name, c_post, c_product, c_version )
        self.client_id = c_id
        
    def getClientDetails(self):
        if not self.client_data:
            self.__printDebug("Client data has not been initialised.  Please use PlexGDM.clientDetails()")

        return self.client_data

    def client_register(self):
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        client_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
        socket.setdefaulttimeout(10)
        self.__printDebug("Sending registration data: %s\n%s" % (self.client_register_header, self.client_data), 3)
        if self.client_data:
            client_sock.sendto("%s\n%s" % (self.client_register_header, self.client_data), self.client_register_group)
            self.client_registered = True
        else:
            self.__printDebug("Client data has not been initialised.  Please use PlexGDM.clientDetails()",3)
            self.client_registered = False

    def client_deregister(self):
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        client_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
        socket.setdefaulttimeout(10)
        self.__printDebug("Sending deregistration data: %s\n%s" % (self.client_deregister_header, self.client_data), 3)
        if self.client_data:
            client_sock.sendto("%s\n%s" % (self.client_deregister_header, self.client_data), self.client_register_group)
            self.client_registered = True
        else:
            self.__printDebug("Client data has not been initialised.  Please use PlexGDM.clientDetails()",3)
            self.client_registered = False

    def check_client_registration(self):
        
        if self.client_registered and self.discovery_complete:

            try:
                media_server=self.server_list[0]['server']
                media_port=self.server_list[0]['port']
                    
                f = urllib2.urlopen('http://%s:%s/clients' % (media_server, media_port))
                if self.client_id in f.read():
                    self.__printDebug("Client registration successful",1)
                    return True
            except:
                self.__printDebug("Unable to check status")
                pass
        
        return False
            
    def getServerList (self):
        return self.server_list
        
    def discover(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Set a timeout so the socket does not block indefinitely
        sock.settimeout(0.2)

        # Set the time-to-live for messages to 1 for local network
        ttl = struct.pack('b', 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

        returnData = []
        try:
            # Send data to the multicast group
            self.__printDebug("Sending discovery messages: %s" % self.discover_message, 2)
            sent = sock.sendto(self.discover_message, self.discover_group)

            # Look for responses from all recipients
            while True:
                try:
                    data, server = sock.recvfrom(1024)
                    self.__printDebug("Received data from %s, %s" % server, 3)
                    self.__printDebug("Data received is:\n %s" % data, 3)
                    returnData.append( { 'from' : server,
                                         'data' : data } )
                except socket.timeout:
                    break
        finally:
            sock.close()

        self.discovery_complete = True

        discovered_servers = []

        if returnData:

            for response in returnData:
                update = { 'server' : response.get('from')[0] }

                #Check if we had a positive HTTP response                        
                if "200 OK" in response.get('data'):
            
                    for each in response.get('data').split('\n'):

                        if "Content-Type:" in each:
                            update['content-type'] = each.split(':')[1].strip()
                        elif "Resource-Identifier:" in each:
                            update['resource-identifier'] = each.split(':')[1].strip()
                        elif "Name:" in each:
                            update['name'] = each.split(':')[1].strip()
                        elif "Port:" in each:
                            update['port'] = each.split(':')[1].strip()
                        elif "Updated-At:" in each:
                            update['updated'] = each.split(':')[1].strip()
                        elif "Version:" in each:
                            update['version'] = each.split(':')[1].strip()

                discovered_servers.append(update)                    

        self.server_list = discovered_servers
    

    def setInterval(self, interval):
        self.discovery_interval = interval

    def stop_all(self):
        self.stop_discovery()
        self.stop_registration()

    def stop_discovery(self):
        if self._discovery_is_running:
            self.__printDebug("Discovery shutting down", 1)
            self._discovery_is_running = False
            self.discover_t.join()
            del self.discover_t
        else:
            self.__printDebug("Discovery not running", 1)

    def stop_registration(self):
        if self._registration_is_running:
            self.__printDebug("Registration shutting down", 1)
            self._registration_is_running = False
            self.register_t.join()
            del self.register_t
            self.client_deregister()
        else:
            self.__printDebug("Registration not running", 1)

    def run_discovery_loop(self):
        #Run initial discovery
        self.discover()

        discovery_count=0
        while self._discovery_is_running:
            discovery_count+=1
            if discovery_count > self.discovery_interval:
                self.discover()
                discovery_count=0
            time.sleep(1)

    def start_discovery(self, daemon = False):
        if not self._discovery_is_running:
            self.__printDebug("Discovery starting up", 1)
            self._discovery_is_running = True
            self.discover_t = threading.Thread(target=self.run_discovery_loop)
            self.discover_t.setDaemon(daemon)
            self.discover_t.start()
        else:
            self.__printDebug("Discovery already running", 1)

    def run_register_loop(self):
       #Run initial registration
        self.client_register()

        registration_count=0
        while self._registration_is_running:
            registration_count+=1
            if registration_count > self.client_interval:
                self.client_register()
                registration_count=0
            time.sleep(1)

    def start_registration(self, daemon = False):
        if not self._registration_is_running:
            self.__printDebug("Registration starting up", 1)
            self._registration_is_running = True
            self.register_t = threading.Thread(target=self.run_register_loop)
            self.register_t.setDaemon(daemon)
            self.register_t.start()
        else:
            self.__printDebug("Registration already running", 1)
             
    def start_all(self, daemon = False):
        self.start_discovery(daemon)
        self.start_registration(daemon)
  

#Example usage
if __name__ == '__main__':
    client = plexgdm(debug=3)
    client.clientDetails("Test-Name", "Test Client", "3003", "Test-App", "1.2.3")
    client.start_all()
    while not client.discovery_complete:
        print "Waiting for results"
        time.sleep(1)
    time.sleep(20)
    print client.getServerList()
    if client.check_client_registration():
        print "Successfully registered"
    else:
        print "Unsuccessfully registered"
    client.stop_all()