# This python generates multiple 'Per-App' AS3 applications in a single as3 declaration where the number of applications 
# equal to the number specified in app_count_list
#
# *** NOTE THAT THE SCRIPT WILL DELETE THE 'Default' TENANT AT THE START ***
#
# This is to ensure a clean config. 
#
# To estimate the performance of automation, after x number of apps have been deployed, 
# the script adds one additional per-app deployment and then deletes it.
#
# Pre-Requisites.
#  
#  Requires AS3 v 3.50.1 or newer, with per-app functionality enabled.
#

import subprocess
import time
import ipaddress
import requests
import json
import base64
import matplotlib.pyplot as plt
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Update the number below to determine how many AS3 apps to deploy.
app_count_list = [2]

# Update the below to match your BIG-IP
mgmt_ip = "18.135.83.133"
bigip_user = "<user>"
bigip_pass = "<password>"


from requests.auth import HTTPBasicAuth
headers = {
'Content-Type': 'application/json'
}


# def apply_terraform():
#     subprocess.run(["terraform", "apply", "-auto-approve"])


def generate_json_body(app_list):
    json_body = {
        "id": "per-app-declaration",
        "schemaVersion": "3.50.0",
        "controls": {
            "class": "Controls"
        }
    }
    
    for app in app_list:
        app_data = {
            "class": "Application",
            f"HTTPS_{app['app_short_name']}": {
                "class": "Service_HTTPS",
                "virtualPort": 443,
                "redirect80": False,
                "virtualAddresses": [
                    app['private_ip']
                ],
                "persistenceMethods": [],
                # "policyWAF": {
                #     "use": f"{app['app_short_name']}_basePolicy" 
                # },
                "profileMultiplex": {
                    "bigip": "/Common/oneconnect"
                },
                "pool": f"{app['app_short_name']}_pool",
                "serverTLS": f"{app['app_short_name']}Tls"
            },
            f"{app['app_short_name']}Tls": {
                "class": "TLS_Server",
                "certificates": [
                    {
                        "certificate": f"{app['app_short_name']}_cert"
                    }
                ]
            },
            f"{app['app_short_name']}_cert": {
                "class": "Certificate",
                "remark": "in practice we recommend using a passphrase",
                "certificate": app['certificate'],
                "privateKey": app['key']
            },
            f"{app['app_short_name']}_pool": {
                "class": "Pool",
                "monitors": [
                    "http"
                ],
                "members": [
                    {
                        "servicePort": 80,
                        "addressDiscovery": "aws",
                        "updateInterval": 1,
                        "tagKey": "Name",
                        "tagValue": app['service_discovery_tag'],
                        "addressRealm": "private",
                        "region": app['region']
                    }
                ]
            }
        }
        
        if app['waf_enable']:
            # add policyWAF to the app
            app_data[f"HTTPS_{app['app_short_name']}"]['policyWAF'] = {
                "use": f"{app['app_short_name']}_basePolicy"
            }
            # add the WAF_policy to the declaration
            app_data[f"{app['app_short_name']}_basePolicy"] = {
                "class": "WAF_Policy",
                "url": "https://raw.githubusercontent.com/s-archer/waf_policies/master/owasp.json",
                "ignoreChanges": False,
                "enforcementMode": "blocking"
            }
        
        json_body[app['app_short_name']] = app_data
    
    return json_body


def generate_app_list(num_apps):
    app_list = []
    for i in range(1, num_apps + 1):
        app_short_name = f"app{i}"
        private_ip = str(ipaddress.IPv4Address('10.0.100.0') + i)
        fqdn = f"{app_short_name}.example.com"
        certificate = "-----BEGIN CERTIFICATE-----\nMIIDiDCCAnACCQDgnXwWSCu0rjANBgkqhkiG9w0BAQsFADCBhTELMAkGA1UEBhMCR0IxDzANBgNVBAgMBkxPTkRPTjEPMA0GA1UEBwwGTE9ORE9OMQswCQYDVQQKDAJGNTENMAsGA1UECwwEVUtTRTEYMBYGA1UEAwwPYXBwMS5mNWRlbW8uY29tMR4wHAYJKoZIhvcNAQkBFg9hcmNoQGY1ZGVtby5jb20wHhcNMjAxMDAyMTU0MTQ2WhcNMjExMDAyMTU0MTQ2WjCBhTELMAkGA1UEBhMCR0IxDzANBgNVBAgMBkxPTkRPTjEPMA0GA1UEBwwGTE9ORE9OMQswCQYDVQQKDAJGNTENMAsGA1UECwwEVUtTRTEYMBYGA1UEAwwPYXBwMS5mNWRlbW8uY29tMR4wHAYJKoZIhvcNAQkBFg9hcmNoQGY1ZGVtby5jb20wggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQD96QENsd6bpVmrC/YqmO5TcsMMnNYshCNqZvU8F25fxHcFdrJR+H9+c6z0yHf6d47Pm2K0fDPRTjofADUiS0U62xE4wRXgvxN7VkUMWdsTKqde8NLPdSkRqDFXIxTPtcLCk11zpSGGV/GqkY4snDaAvZWQY/qG5ozSqjMbBYAL0FC9sZl7ZSK4FaPkfN8fImR+gTAXEOja1IOyFNgfKJZ2nQW0l79kiNR4lkWgGhrTTI+twx9DHMiKdKZe/fg5Ac2rVMnByM+W4kLHxfu5+pIsp8r4J4jSmUSOUbpFpImScUbVncL5Q+ge9sIk0eaEOGV4foKcyWT5OGhLzM9pq2o7AgMBAAEwDQYJKoZIhvcNAQELBQADggEBAOxe5A6PDt71mgBsn8OccoeLOcreeMmNz1WgNkO+tKjpQyGd2gLUufLXRPdu87MyBC7+fbV84fNtWvMS+19KkprddXNJwVEYo0XUx9o+02lUZPK6GiNK92+ztL81b+7v7/NoiDmG8vWAKDZcX7t+epQDwEOU4vqBaejSzZAkQqVHtEonrdn/IHCD0nST9yDU5z+klT4Auat7KJbdCTlnpmrt/8pZyzyEsZevPvsEl4oVNEdrTtdXEV5S7W+jE4iPQZ/PQriZWKPh5NRIPtHAc8ewxEkhyg9OW+REVR/EV43pACgqUhma0Og7BgA+jQz86je3OZOY2Sj4DXtZROAEvCM=\n-----END CERTIFICATE-----"
        key = "-----BEGIN PRIVATE KEY-----\nMIIEwAIBADANBgkqhkiG9w0BAQEFAASCBKowggSmAgEAAoIBAQD96QENsd6bpVmr\nC/YqmO5TcsMMnNYshCNqZvU8F25fxHcFdrJR+H9+c6z0yHf6d47Pm2K0fDPRTjof\nADUiS0U62xE4wRXgvxN7VkUMWdsTKqde8NLPdSkRqDFXIxTPtcLCk11zpSGGV/Gq\nkY4snDaAvZWQY/qG5ozSqjMbBYAL0FC9sZl7ZSK4FaPkfN8fImR+gTAXEOja1IOy\nFNgfKJZ2nQW0l79kiNR4lkWgGhrTTI+twx9DHMiKdKZe/fg5Ac2rVMnByM+W4kLH\nxfu5+pIsp8r4J4jSmUSOUbpFpImScUbVncL5Q+ge9sIk0eaEOGV4foKcyWT5OGhL\nzM9pq2o7AgMBAAECggEBAKBErdSOHFwUb9gGkdhrdauYucNBT/MDaTNlT5Ahnhq2\n8QWy2XXiK9+OdnKAAzNGug8THqeb6j1IamldASznZAh1dJZlUkDteweT+buFEEI1\n3zWPPxGR+11Y0+QTkbRWH1wgFpHDfrjE1Bb9D0fbRo/Wmwxr/xuddPAYXG/G9f79\nuc19OTKxyQexJinOVlnmhWyT6jwYtedd8kcrcpBbV13TEvRpuWvYqoh8iCsUL1oM\nsqH59z1f5j3gEDfnGurZxW78+5tGq3ZsbUbwU+oTROeBBo0WJLCWno4UIUCpvdt3\ni1i8A+/MKEpODwy6qcSEKFrlUsXXPH8s0HmFxDOHIFECgYEA/1e81muSoGk5LkU2\n9XCCV5ODKAXFv1KDGAnhYKrJxm6N/msgfk/77pQxjHffAHv22uOJrnlv5pnHGx1N\npgCXyh+EkITSAgG754PJCYdtsKIl4wJqyK7/k8ziFi9NS1GHg1dfCAJcNbE+3Yfj\n1PN8L1xfpVB2KBAFVrA+/GpJSdkCgYEA/pBSjPy0wzdjFcyxksTt6x8z4P5FPWWp\n0C0emCym/0FEy6uJf7xCJp99feeTzNQhxjNCGmgQKTbvJD4vHl38iZJ4ObtLaGM3\nJ2p+00CfMWSMLb2nGsJQqkjH3L6M9/T/COIWkzxD6VFar4qrYNB1bye525B5EoeM\nkbOTiB761DMCgYEA2htrpgwFFxhKS4e7xjLwYzYRliI4I5CrgeEOrq+z4teUWnnP\nK5XOsJ/NIxtRVOyOk7JAbNQ2DVfVhwekx+NBxNjfN0L8z9IDW2JqWsVfoL0gd6Qc\n6obwsKMVi7Wj5G4jvsDm38SEVyirdjcZGVFSBnJ1EJSGGPp2VPH/G0T+jSECgYEA\nl6hbxer3tiXVPjOIxyvTonQgcDaMAZwDoyZ+R6KyivfTiJNVg2gg8Omr1cqVXz4y\nMOZwx1Kf7i3wIuN5JtpPjZZZUeunbTVOsojbrfed38tLSCTo3SRO8mQRzg0n5sFq\n/1vSnz0UKHhzUomGuFL445QDQi+8MbHXqSYXCs2KGckCgYEA35ljj09Kei2/llEw\n9Z1A0t67fZNyfsyDVEba+w1iMYsp7RAUw+jvGugbOeQX0xvgVW0+88X2mgoF11X7\nN0DjDz6mpnmDrSt3YmOOAWoudjeh/EcIcNmMPiUwNtIBqqXdX4NqZdQqhRtYFYre\nPBTinj1QkAVu3I3aiVKNQOk8vt4=\n-----END PRIVATE KEY-----"
        encoded_certificate = base64.b64encode(certificate.encode()).decode()
        passphrase = ""
        protected = ""
        service_discovery_tag = f"{app_short_name}-tag"
        region = "eu-west-2"
        waf_enable = False

        app = {
            "app_short_name": app_short_name,
            "private_ip": private_ip,
            "fqdn": fqdn,
            "certificate": certificate,
            "key": key,
            "passphrase": passphrase,
            "protected": protected,
            "service_discovery_tag": service_discovery_tag,
            "region": region,
            "waf_enable": waf_enable
        }

        app_list.append(app)

    return app_list


def generate_per_app_body():
    per_app_body = json.dumps({
    "id": "per-app-declaration",
    "schemaVersion": "3.50.0",
    "controls": {
        "class": "Controls",
        "logLevel": "debug",
        "trace": True
    },
    "app-10001": {
        "class": "Application",
        "service": {
        "class": "Service_HTTP",
        "virtualAddresses": [
            "10.0.12.245"
        ],
        "pool": "pool-10001"
        },
        "pool-10001": {
        "class": "Pool",
        "members": [
            {
            "servicePort": 80,
            "serverAddresses": [
                "192.0.12.11",
                "192.0.12.21"
            ]
            }
        ]
        }
    }
    })
    
    return per_app_body


def delete_tenant():
    url = "https://" + mgmt_ip + "/mgmt/shared/appsvcs/declare/Default"
    headers = {
    'Content-Type': 'application/json'
    }
    print("About to DELETE Tenant Default: " + url)
    response = requests.request("DELETE", url, headers=headers, verify=False, auth=HTTPBasicAuth(bigip_user, bigip_pass))
    print(response.text)
    response_dict = json.loads(response.text)
    print(json.dumps(response_dict, indent=4))


def as3(payload, count, method):
    url = "https://" + mgmt_ip + "/mgmt/shared/appsvcs/declare/Default/applications"
    if method == "DELETE":
        url = url + "/app-10001"
    # print(f"About to CREATE {count} Apps: " + url)
    try:
        response = requests.request(method, url, headers=headers, data=payload, verify=False, auth=HTTPBasicAuth(bigip_user, bigip_pass))
        # print(response.text)
        if response.status_code == 200:
            print("\nRequest successful. Continue.\n")
            return response.status_code
        elif response.status_code == 202:
            response_json = response.json()
            self_link = response_json.get("selfLink")
            if self_link:
                self_link = self_link.replace("localhost", mgmt_ip)
                print("Request accepted. Self link:", self_link)
                poll_result = poll_task(self_link)
                if poll_result:
                    print("Poll completed successfully.")
                    return response.status_code
                else:
                    print("Poll failed or encountered an error.")
                    return False
            else:
                print("Error: No selfLink found in the response body.")
                return False
        else:
            print("Error:", response.status_code, response.text)
            return False
    except requests.RequestException as e:
        print("Request failed:", e)
        return False


def poll_task(self_link):
    while True:
        print("Polling for status:", self_link)
        poll_response = requests.get(self_link, headers=headers, verify=False, auth=HTTPBasicAuth(bigip_user, bigip_pass))
        # Print out the response content for debugging
        # print("Response content:", poll_response.text)
        
        try:
            poll_data = poll_response.json()
            message = poll_data['results'][0]['message']
        
            if message == 'in progress':
                print("Task is still in progress. Waiting for completion...")
                time.sleep(1)  # Wait for 1 second before polling again
            elif message == 'declaration failed':
                print("Task failed:", message)
                # Handle error or raise an exception as per your requirement
                return False
            elif message == 'success':
                print("Poll task completed successfully.")
                # Continue with your further logic or return
                return True
            else:
                print("Unexpected message received:", message)
                # Handle unexpected message or raise an exception
                return False

        except Exception as e:
            print("Error parsing JSON:", e)
            # Handle the error or raise an exception
            return False


def plot_execution_times(app_counts, apply_times, add_app_times, delete_app_times, polling):
    plt.plot(app_counts, apply_times, label='Apply X Per-Apps in Single Declare')
    plt.plot(app_counts, add_app_times, label='Single Additional Per-App Time')
    plt.plot(app_counts, delete_app_times, label='Single Delete Per-App Time')
    plt.plot(app_counts, polling, label='Async Mode')
    # Plot the on/off state as a horizontal line
    # plt.axhline(y=polling, color='r', linestyle='--', label='On/Off State')
    # plt.text(app_counts[-1] + 10, polling, 'On/Off', verticalalignment='center')

    plt.xlabel('Number of Apps')
    plt.ylabel('Time (seconds)')
    plt.title('Execution Times vs Number of Apps')
    plt.legend()
    plt.savefig("./performance_graph.png")
    plt.show()
    

def main():
    resource_counts = app_count_list
    apply_times = []
    per_app_create_times = []
    per_app_delete_times = []
    poll_status = []

    # start with clean slate
    delete_tenant()

    for count in resource_counts:
        print(f"\n----------------------------------------\n")
        print(f"Applying {count} per-app applications...")
        app_list = generate_app_list(count)
        generated_json = json.dumps(generate_json_body(app_list), indent=4)
        # Open the file in write mode and write the JSON string to it
        with open('./declarations/as3-declaration.json', 'w') as file:
            file.write(generated_json)
        per_app_body = generate_per_app_body()

        try:
            start_time = time.time()
            # apply_terraform()
            result = as3(generated_json, count, "POST")
            if result:
                end_time = time.time()
                apply_time = end_time - start_time
                apply_times.append(apply_time)
                print(f"Applied {count} resources in {apply_time:.2f} seconds\n")
                if result == 200:
                    poll_status.append(1)
                else:
                    poll_status.append(100)
            else:
                print(f"Failed to apply {count} resources. AS3 failed.\n")
                apply_times.append(None)
                poll_status.append(None)

        except subprocess.CalledProcessError as e:
            print(f"Failed to apply {count} resources. Error: {e}\n")
            apply_times.append(None)
            poll_status.append(None)

        try:
            # Send a single per app, in addition, for timing purposes.
            start_time = time.time()
            print(f"About to add single per-app, on top of {count} apps\n")
            as3(per_app_body, count, "POST")
            end_time = time.time()
            apply_time = end_time - start_time
            per_app_create_times.append(apply_time)
            print(f"Added single per-app, on top of {count} apps in {apply_time:.2f} seconds\n")
        
        except subprocess.CalledProcessError as e:
            print(f"Failed to add single per-app, on top of {count} resources. Error: {e}\n")
            per_app_create_times.append(None)
        
        try:
            # Delete a single per app, in addition, for timing purposes.
            start_time = time.time()
            print(f"About to delete single per-app, on top of {count} apps\n")
            as3("", count, "DELETE")
            end_time = time.time()
            apply_time = end_time - start_time
            per_app_delete_times.append(apply_time)
            print(f"Deleted single per-app, on top of {count} apps in {apply_time:.2f} seconds\n")

        except subprocess.CalledProcessError as e:
            print(f"Failed to delete single per-app, on top of {count} resources. Error: {e}\n")
            per_app_delete_times.append(None)

    print("\nSummary:")

    for idx, count in enumerate(resource_counts):
        if apply_times[idx] is not None:
            print(f"Applied {count} resources in {apply_times[idx]:.2f} seconds")
            print(f"Added single per-app, on top of {count} apps in {per_app_create_times[idx]:.2f} seconds")
            print(f"Deleted single per-app, on top of {count} apps in {per_app_delete_times[idx]:.2f} seconds")
        else:
            print(f"Failed to apply {count} resources")

    plot_execution_times(app_count_list, apply_times, per_app_create_times, per_app_delete_times, poll_status)
    

if __name__ == "__main__":
    main()