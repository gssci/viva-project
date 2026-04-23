import objc
from Foundation import NSObject, NSRunLoop, NSDate
import CoreLocation
import sys

class LocationDelegate(NSObject):
    def locationManager_didUpdateLocations_(self, manager, locations):
        """Callback for when the OS successfully finds the location."""
        location = locations.lastObject()
        coords = location.coordinate()
        accuracy = location.horizontalAccuracy()
        
        print(f"Latitude:  {coords.latitude}")
        print(f"Longitude: {coords.longitude}")
        print(f"Accuracy:  Within {accuracy} meters")
        
        # Stop the hardware from updating to save power, and flag that we are done
        manager.stopUpdatingLocation()
        self.done = True

    def locationManager_didFailWithError_(self, manager, error):
        """Callback for when the OS fails to find the location."""
        print(f"Error getting location: {error.localizedDescription()}")
        manager.stopUpdatingLocation()
        self.done = True

def get_precise_location():
    # Initialize the Location Manager and our custom Delegate
    manager = CoreLocation.CLLocationManager.alloc().init()
    delegate = LocationDelegate.alloc().init()
    delegate.done = False
    
    manager.setDelegate_(delegate)

    # Check if the user has explicitly denied location access
    auth_status = CoreLocation.CLLocationManager.authorizationStatus()
    if auth_status in [CoreLocation.kCLAuthorizationStatusRestricted, 
                       CoreLocation.kCLAuthorizationStatusDenied]:
        print("Location access denied. Please grant permission in System Settings -> Privacy & Security.")
        sys.exit(1)

    print("Querying macOS Core Location... (This may take a few seconds)")
    manager.startUpdatingLocation()

    # Core Location is asynchronous. We must run an event loop to catch the callback.
    run_loop = NSRunLoop.currentRunLoop()
    while not delegate.done:
        # Run the loop in 0.1-second increments until the delegate fires
        run_loop.runMode_beforeDate_("NSDefaultRunLoopMode", NSDate.dateWithTimeIntervalSinceNow_(0.1))

if __name__ == "__main__":
    get_precise_location()