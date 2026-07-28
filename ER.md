```mermaid
erDiagram
    Company ||--o{ AuthUser : has
    Company ||--o{ User : has
    Company ||--o{ Client : has
    Company ||--o{ Device : owns
    Company ||--o{ TransmissionStation : owns
    Company ||--o{ CompanyDefaults : configures
    Company ||--o{ DeviceTypeTemplate : defines
    
    AuthUser {
        int id PK
        string username UK
        string email UK
        string password_hash
        string role
        boolean is_active
        int company_id FK
        string phone_number
        boolean can_add_device
        boolean can_delete_device
        boolean can_restart_device
        boolean can_configure_device
        datetime created_at
    }
    
    User {
        int id PK
        string full_name
        string email UK
        string alias
        string password_hash
        string role
        int company_id FK
        datetime created_at
    }
    
    Client {
        int id PK
        string name
        string location
        string contact_info
        int company_id FK
        datetime created_at
    }
    
    Device ||--o| Client : belongs_to
    Device ||--o| TransmissionStation : located_at
    Device ||--o| Sector : assigned_to
    Device ||--o{ NetworkInterface : has
    Device ||--o{ ConfigHistory : has
    Device ||--o{ Backup : archived_in
    Device ||--o{ DHCPLease : provides
    Device ||--o{ DHCPConfig : configured_by
    Device ||--o{ RoutingTable : maintains
    Device ||--o{ FirewallRule : enforces
    Device }o--|| Device : "parent_of"
    
    Device {
        string device_id PK
        string mac_address UK
        string name
        string description
        string ip_address
        string ip_type
        string netmask
        string pppoe_username
        string pppoe_password
        string model
        string device_type
        string ssid
        string status
        string firmware_version
        int snr
        json credentials
        int client_id FK
        int company_id FK
        int sector_id FK
        int station_id FK
        string parent_device_id FK
        datetime created_at
        datetime last_seen
        int uptime
        string last_config_hash
        int needs_restore
    }
    
    TransmissionStation ||--o{ Sector : contains
    TransmissionStation ||--o{ Device : hosts
    TransmissionStation }o--|| TransmissionStation : "uplink_to"
    
    TransmissionStation {
        int id PK
        string name
        string location
        boolean is_gateway
        int company_id FK
        string station_type
        int parent_id FK
        string link_device_id
        string device_model
    }
    
    Sector {
        int id PK
        string name
        int station_id FK
        string mac_address
        string device_model
        string horn_orientation
        string ip_type
        string ip_address
        string netmask
    }
    
    NetworkInterface {
        int id PK
        string device_id FK
        string name
        string mac_address
        string description
        string ip_address
        string ipv6_address
        string netmask
        int mtu
        int speed
        string duplex
        string admin_state
        string oper_state
        int rx_bytes
        int tx_bytes
        int rx_packets
        int tx_packets
        int rx_errors
        int tx_errors
        string vlan
        json neighbors
        json config_snapshot
        datetime last_change
        datetime last_seen
    }
    
    Backup {
        string backup_id PK
        string device_id FK
        datetime timestamp
        string note
        string config_json
    }
    
    ConfigHistory {
        int id PK
        string device_id FK
        string note
        datetime timestamp
        json config_snapshot
    }
    
    EventLog {
        int id PK
        int company_id FK
        string device_id FK
        string username
        string activity_type
        string message
        string severity
        json details
        datetime timestamp
    }
    
    AuditLog {
        int id PK
        int user_id
        string username
        string action
        string target_type
        string target_id
        json details
        datetime timestamp
    }
    
    Invitation {
        int id PK
        string token UK
        string email
        string full_name
        string alias
        string phone_number
        int company_id FK
        string role
        datetime created_at
    }
    
    CompanyDefaults {
        int id PK
        int company_id FK UK
        string dns_primary
        string dns_secondary
        string ntp_server
        string syslog_server
        string snmp_community
        string admin_username
        string enable_password
        string domain_name
        string management_acl
        datetime created_at
    }
    
    DeviceTypeTemplate {
        int id PK
        int company_id FK
        string device_type
        string template_name
        string config_content
        boolean is_default
        datetime created_at
    }
    
    DHCPConfig {
        int id PK
        string device_id FK
        boolean enabled
        string range_start
        string range_end
        string dns_server
        int lease_time
    }
    
    DHCPLease {
        int id PK
        string device_id FK
        string client_mac
        string client_ip
        datetime lease_start
        datetime lease_end
    }
    
    RoutingTable {
        int id PK
        string device_id FK
        string destination
        string gateway
        int metric
    }
    
    FirewallRule {
        int id PK
        string device_id FK
        string rule_type
        int port
        string protocol
        string desc
    }
```