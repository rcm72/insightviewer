# Insight Viewer

## Overview
The Insight Viewer is a web application built using Flask that allows users to visualize and manipulate graph data. It features an HTML editor for customizing visualizations and a template system for loading predefined HTML structures.

## Project Structure
```
insight-viewer
├── app.py                     # Main Flask application
├── requirements.txt           # Project dependencies
├── templates                  # HTML templates
│   ├── index.html             # Main application interface
│   └── choose_template_dialog.html # Dialog for choosing templates
├── static                     # Static files (CSS, JS)
│   ├── css
│   │   └── index.css          # Styles for the application
│   ├── js
│   │   ├── indexScript.js     # Main JavaScript for application logic
│   │   └── templatesTabulator.js # JavaScript for managing templates table
│   └── vendor
│       └── tabulator.min.js   # Tabulator library for interactive tables
├── templates_data             # Directory for template files
│   └── sample_templates
│       └── example_template.html # Example HTML template
└── README.md                  # Project documentation
```

## Setup Instructions
1. **Clone the repository**:
   ```
   git clone <repository-url>
   cd insight-viewer
   ```

2. **Install dependencies**:
   It is recommended to use a virtual environment. You can create one using:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```
   Then install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. **Run the application**:
   Start the Flask server by running:
   ```
   python app.py
   ```
   The application will be accessible at `http://127.0.0.1:5000`.

## Usage
- Open the application in your web browser.
- Use the HTML editor to create or modify visualizations.
- Click on the "Load Template" button to choose from available templates.
- The selected template will be loaded into the HTML editor for further customization.

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for details.