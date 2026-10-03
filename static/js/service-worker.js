self.addEventListener("push", function (event) {

    let data = {};

    if (event.data) {
        data = event.data.json();
    }

    const title = data.title || "Smart Medicine Reminder";

    const options = {
        body: data.body || "It is time to take your medicine.",
        icon: "/static/images/medicine-icon.png",
        badge: "/static/images/medicine-icon.png",
        data: {
            url: "/dashboard"
        }
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});


self.addEventListener("notificationclick", function (event) {

    event.notification.close();

    event.waitUntil(
        clients.openWindow(
            event.notification.data.url
        )
    );

});